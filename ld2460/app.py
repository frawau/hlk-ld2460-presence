from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from .protocol import FrameReader
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


async def run_pipeline(
    reader: ByteReader,
    tracker: Tracker,
    reporters: Sequence[Reporter],
    *,
    clock: Callable[[], float] = time.monotonic,
    read_size: int = 256,
    stop=None,
) -> None:
    """Drive the decode pipeline until EOF or `stop` is set.

    reader: object with ``async read(n) -> bytes`` (serial stream or fake).
    stop:   optional asyncio.Event for graceful shutdown.
    """
    frame_reader = FrameReader()
    started: list[Reporter] = []
    try:
        for r in reporters:
            await r.start()
            started.append(r)
        while stop is None or not stop.is_set():
            data = await _read_or_stop(reader, read_size, stop)
            if data is None:  # stop fired during the read
                break
            if not data:  # EOF
                break
            for targets in frame_reader.feed(data):
                report = tracker.update(targets, clock())
                for r in reporters:
                    await r.report(report)
    finally:
        for r in started:
            await r.close()
