from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

from .protocol import FrameReader
from .reporters import Reporter
from .tracking import Tracker


class ByteReader(Protocol):
    async def read(self, n: int) -> bytes: ...


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

    reader: object with `async read(n) -> bytes` (serial stream or fake).
    stop:   optional asyncio.Event for graceful shutdown.
    """
    frame_reader = FrameReader()
    for r in reporters:
        await r.start()
    try:
        while stop is None or not stop.is_set():
            data = await reader.read(read_size)
            if not data:
                break
            for targets in frame_reader.feed(data):
                report = tracker.update(targets, clock())
                for r in reporters:
                    await r.report(report)
    finally:
        for r in reporters:
            await r.close()
