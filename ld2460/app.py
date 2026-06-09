from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

from .model import PresenceReport
from .protocol import FrameReader, enable_reporting
from .reporters import Reporter
from .tracking import Tracker


class ByteReader(Protocol):
    async def read(self, n: int) -> bytes: ...


async def _read_or_stop(reader: ByteReader, n: int, stop) -> bytes | None:
    """Read up to n bytes, or return None if `stop` fires first.

    Without `stop`, this is a plain ``await reader.read(n)``. With `stop`, the
    read is raced against the stop event so a blocked read on an idle serial
    port does not prevent graceful shutdown.
    """
    if stop is None:
        return await reader.read(n)
    read_task = asyncio.ensure_future(reader.read(n))
    stop_task = asyncio.ensure_future(stop.wait())
    done, pending = await asyncio.wait(
        {read_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    for task in pending:
        try:
            await task
        except asyncio.CancelledError:
            pass
    if read_task in done:
        return read_task.result()
    return None


async def iter_reports(
    reader: ByteReader,
    tracker: Tracker,
    *,
    clock: Callable[[], float] = time.monotonic,
    read_size: int = 256,
    stop=None,
) -> AsyncIterator[PresenceReport]:
    """Yield one PresenceReport per decoded radar frame until EOF or `stop`.

    The programmatic integration seam: drive it from your own code to consume
    presence updates without writing a Reporter::

        reader, _ = await open_byte_stream("/dev/ttyACM0")
        async for report in iter_reports(reader, Tracker()):
            ...
    """
    frame_reader = FrameReader()
    while stop is None or not stop.is_set():
        data = await _read_or_stop(reader, read_size, stop)
        if data is None or not data:  # stop fired, or EOF
            break
        for targets in frame_reader.feed(data):
            yield tracker.update(targets, clock())


async def run_pipeline(
    reader: ByteReader,
    tracker: Tracker,
    reporters: Sequence[Reporter],
    *,
    clock: Callable[[], float] = time.monotonic,
    read_size: int = 256,
    stop=None,
) -> None:
    """Drive the decode pipeline, sending each report to every reporter.

    Starts reporters before the loop and closes them in a finally.
    """
    started: list[Reporter] = []
    try:
        for r in reporters:
            await r.start()
            started.append(r)
        async for report in iter_reports(
            reader, tracker, clock=clock, read_size=read_size, stop=stop
        ):
            for r in reporters:
                await r.report(report)
    finally:
        for r in started:
            await r.close()


async def stream_presence(
    port: str = "/dev/ttyACM0",
    baud: int = 115200,
    *,
    tracker: Tracker | None = None,
    enable_on_start: bool = False,
    clock: Callable[[], float] = time.monotonic,
    read_size: int = 256,
    stop=None,
    **tracker_kwargs,
) -> AsyncIterator[PresenceReport]:
    """Open the serial port and yield PresenceReports — the one-call integration.

    Pass ``tracker=`` a preconfigured Tracker, or tracker_kwargs
    (static_threshold, gate, age_out, smoothing, min_samples) to build one.
    Closes the port on exit::

        async for report in stream_presence("/dev/ttyACM0", static_threshold=0.1):
            rdm.handle(report)
    """
    from .transport import open_byte_stream

    reader, writer = await open_byte_stream(port, baud)
    try:
        if enable_on_start:
            writer.write(enable_reporting())
            await writer.drain()
        tk = tracker if tracker is not None else Tracker(**tracker_kwargs)
        async for report in iter_reports(
            reader, tk, clock=clock, read_size=read_size, stop=stop
        ):
            yield report
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # pragma: no cover - best-effort close
            pass
