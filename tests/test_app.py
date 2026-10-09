import asyncio
import itertools

import pytest

from ld2460.app import iter_reports, run_pipeline, stream_presence
from ld2460.model import Motion
from ld2460.protocol import build_report_frame, enable_reporting
from ld2460.reporters import Reporter
from ld2460.tracking import Tracker


class FakeReader:
    """Yields each queued chunk once, then b'' to signal EOF."""

    def __init__(self, chunks):
        self._chunks = list(chunks) + [b""]
        self._i = 0

    async def read(self, _n):
        chunk = self._chunks[self._i]
        self._i += 1
        return chunk


class RecordingReporter(Reporter):
    def __init__(self):
        self.reports = []
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def report(self, report):
        self.reports.append(report)

    async def close(self):
        self.closed = True


async def test_pipeline_decodes_and_reports():
    # Person approaching: distance shrinks frame to frame.
    frames = [build_report_frame([(0.0, 3.0 - i * 0.4)]) for i in range(5)]
    reader = FakeReader(frames)
    rec = RecordingReporter()
    clock = itertools.count(0, 1)  # 0,1,2,... deterministic seconds
    await run_pipeline(reader, Tracker(min_samples=3), [rec], clock=lambda: next(clock))
    assert rec.started and rec.closed
    assert len(rec.reports) == 5
    assert rec.reports[-1].count == 1
    assert rec.reports[-1].persons[0].motion is Motion.APPROACHING


async def test_pipeline_stops_on_eof():
    reader = FakeReader([])  # immediately EOF
    rec = RecordingReporter()
    await run_pipeline(reader, Tracker(), [rec], clock=lambda: 0.0)
    assert rec.reports == []
    assert rec.closed


async def test_pipeline_handles_frame_split_across_reads():
    frame = build_report_frame([(0.0, 2.0)])
    reader = FakeReader([frame[:3], frame[3:]])
    rec = RecordingReporter()
    clock = itertools.count(0, 1)
    await run_pipeline(reader, Tracker(), [rec], clock=lambda: next(clock))
    assert len(rec.reports) == 1
    assert rec.reports[0].count == 1


async def test_pipeline_exits_when_stop_set_during_blocking_read():
    stop = asyncio.Event()

    class BlockingReader:
        async def read(self, _n):
            await asyncio.Event().wait()  # blocks forever

    rec = RecordingReporter()

    async def trigger():
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.wait_for(
        asyncio.gather(
            run_pipeline(
                BlockingReader(), Tracker(), [rec], clock=lambda: 0.0, stop=stop
            ),
            trigger(),
        ),
        timeout=2.0,
    )
    assert rec.started and rec.closed


async def test_iter_reports_yields_per_frame():
    frames = [build_report_frame([(0.0, 2.0)]) for _ in range(3)]
    reader = FakeReader(frames)
    clock = itertools.count(0, 1)
    reports = [
        r async for r in iter_reports(reader, Tracker(), clock=lambda: next(clock))
    ]
    assert len(reports) == 3
    assert all(r.count == 1 for r in reports)


async def test_stream_presence_opens_port_and_yields(monkeypatch):
    frames = [build_report_frame([(0.0, 2.0)]) for _ in range(2)]
    reader = FakeReader(frames)

    class FakeWriter:
        def write(self, _b):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def fake_open(port, baud=115200):
        return reader, FakeWriter()

    import ld2460.transport

    monkeypatch.setattr(ld2460.transport, "open_byte_stream", fake_open)
    clock = itertools.count(0, 1)
    reports = [
        r async for r in stream_presence("/dev/whatever", clock=lambda: next(clock))
    ]
    assert len(reports) == 2
    assert reports[-1].count == 1


async def test_stream_presence_uses_ble_when_requested(monkeypatch):
    frames = [build_report_frame([(0.0, 2.0)])]
    reader = FakeReader(frames)
    opened = []

    class FakeWriter:
        def write(self, _b):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def fake_open_ble(address):
        opened.append(address)
        return reader, FakeWriter()

    async def no_serial(*_a, **_k):
        raise AssertionError("serial must not be opened")

    import ld2460.ble
    import ld2460.transport

    monkeypatch.setattr(ld2460.ble, "open_ble_stream", fake_open_ble)
    monkeypatch.setattr(ld2460.transport, "open_byte_stream", no_serial)
    reports = [
        r async for r in stream_presence(ble="89:EC:12:F6:6A:62", reconnect=False)
    ]
    assert opened == ["89:EC:12:F6:6A:62"]
    assert len(reports) == 1


class _NullWriter:
    def __init__(self):
        self.written = []
        self.closed = False

    def write(self, b):
        self.written.append(b)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def _fake_ble_opener(monkeypatch, sessions):
    """Patch open_ble_stream to replay `sessions`: an exception or a frame list."""
    import ld2460.ble

    writers = []
    calls = iter(sessions)

    async def fake_open(address):
        session = next(calls)
        if isinstance(session, Exception):
            raise session
        writer = _NullWriter()
        writers.append(writer)
        return FakeReader(session), writer

    monkeypatch.setattr(ld2460.ble, "open_ble_stream", fake_open)
    return writers


async def test_ble_reconnects_after_disconnect_and_failed_connect(monkeypatch):
    frame = build_report_frame([(0.0, 2.0)])
    writers = _fake_ble_opener(
        monkeypatch,
        [[frame, frame], ConnectionError("not found"), [frame]],
    )
    stop = asyncio.Event()
    reports = []
    async for r in stream_presence(
        ble="auto", stop=stop, enable_on_start=True, retry_delay=0
    ):
        reports.append(r)
        if len(reports) == 3:
            stop.set()
    assert len(reports) == 3
    assert len(writers) == 2
    # enable-reporting is re-sent on every new connection; each one is closed.
    assert all(w.written == [enable_reporting()] and w.closed for w in writers)


async def test_ble_reconnect_can_be_disabled(monkeypatch):
    frame = build_report_frame([(0.0, 2.0)])
    _fake_ble_opener(monkeypatch, [[frame], [frame]])
    reports = [r async for r in stream_presence(ble="auto", reconnect=False)]
    assert len(reports) == 1


async def test_failed_first_connect_raises_without_reconnect(monkeypatch):
    _fake_ble_opener(monkeypatch, [ConnectionError("not found")])
    with pytest.raises(ConnectionError):
        async for _ in stream_presence(ble="auto", reconnect=False):
            pass


async def test_stop_interrupts_reconnect_wait(monkeypatch):
    _fake_ble_opener(monkeypatch, [ConnectionError("x")] * 5)
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.05, stop.set)
    reports = [r async for r in stream_presence(ble="auto", stop=stop, retry_delay=30)]
    assert reports == []


async def test_serial_does_not_reconnect_by_default(monkeypatch):
    frame = build_report_frame([(0.0, 2.0)])
    opens = []

    async def fake_open(port, baud=115200):
        opens.append(port)
        return FakeReader([frame]), _NullWriter()

    import ld2460.transport

    monkeypatch.setattr(ld2460.transport, "open_byte_stream", fake_open)
    reports = [r async for r in stream_presence("/dev/x")]
    assert len(reports) == 1 and opens == ["/dev/x"]


async def test_multiple_radars_error_is_not_retried(monkeypatch):
    from ld2460.ble import MultipleRadarsError

    _fake_ble_opener(monkeypatch, [MultipleRadarsError([]), [build_report_frame([])]])
    with pytest.raises(MultipleRadarsError):
        async for _ in stream_presence(ble="auto", retry_delay=0):
            pass


async def test_auto_reconnects_to_the_radar_it_found(monkeypatch):
    import ld2460.ble

    frame = build_report_frame([(0.0, 2.0)])
    addresses = []

    class AddressedWriter(_NullWriter):
        address = "89:EC:12:F6:6A:62"

    async def fake_open(address):
        addresses.append(address)
        return FakeReader([frame]), AddressedWriter()

    monkeypatch.setattr(ld2460.ble, "open_ble_stream", fake_open)
    stop = asyncio.Event()
    async for _ in stream_presence(ble="auto", stop=stop, retry_delay=0):
        if len(addresses) == 2:
            stop.set()
    assert addresses == ["auto", "89:EC:12:F6:6A:62"]
