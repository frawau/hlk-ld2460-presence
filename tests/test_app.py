import asyncio
import itertools

from ld2460.app import run_pipeline
from ld2460.model import Motion
from ld2460.protocol import build_report_frame
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
