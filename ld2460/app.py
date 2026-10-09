from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

from .ble import DISCOVERY_MODES, MultipleRadarsError
from .model import PresenceReport
from .protocol import FrameReader, enable_reporting
from .reporters import Reporter
from .tracking import Tracker

log = logging.getLogger(__name__)


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
    await deliver_reports(
        iter_reports(reader, tracker, clock=clock, read_size=read_size, stop=stop),
        reporters,
    )


async def deliver_reports(
    reports: AsyncIterator[PresenceReport], reporters: Sequence[Reporter]
) -> None:
    """Send every report from `reports` to each reporter until it is exhausted.

    Starts reporters before the loop and closes them in a finally.
    """
    started: list[Reporter] = []
    try:
        for r in reporters:
            await r.start()
            started.append(r)
        async for report in reports:
            for r in reporters:
                await r.report(report)
    finally:
        for r in started:
            await r.close()


async def _sleep_or_stop(delay: float, stop) -> None:
    if stop is None:
        await asyncio.sleep(delay)
        return
    try:
        await asyncio.wait_for(stop.wait(), delay)
    except asyncio.TimeoutError:
        pass


async def _await_or_stop(coro, stop):
    """Await `coro`; if `stop` fires first, cancel it and return None."""
    if stop is None:
        return await coro
    task = asyncio.ensure_future(coro)
    stop_task = asyncio.ensure_future(stop.wait())
    await asyncio.wait({task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    stop_task.cancel()
    if task.done():
        return task.result()
    task.cancel()
    try:
        await task
    except BaseException:
        pass
    return None


async def _close(writer) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:  # pragma: no cover - best-effort close
        pass


async def stream_presence(
    port: str = "/dev/ttyACM0",
    baud: int = 115200,
    *,
    ble: str | None = None,
    reconnect: bool | None = None,
    retry_delay: float = 2.0,
    max_retry_delay: float = 60.0,
    tracker: Tracker | None = None,
    enable_on_start: bool = False,
    clock: Callable[[], float] = time.monotonic,
    read_size: int = 256,
    stop=None,
    **tracker_kwargs,
) -> AsyncIterator[PresenceReport]:
    """Open the radar and yield PresenceReports — the one-call integration.

    Reads the serial `port` by default; pass ``ble=`` a MAC address (or
    ``"auto"``) to connect over Bluetooth LE instead (needs the [ble] extra).
    Pass ``tracker=`` a preconfigured Tracker, or tracker_kwargs
    (static_threshold, gate, age_out, smoothing, min_samples) to build one.
    Closes the connection on exit::

        async for report in stream_presence("/dev/ttyACM0", static_threshold=0.1):
            rdm.handle(report)

    With `reconnect` (default: on for BLE, off for serial) a lost connection,
    or a failed connection attempt, is retried after `retry_delay` seconds,
    doubling up to `max_retry_delay`; the delay resets once data flows again.
    The stream then only ends when `stop` is set. Without it, the first
    disconnect ends the stream and a failed connect raises.

    ``ble="auto"`` needs exactly one LD2460 in range; with several it raises
    `ld2460.ble.MultipleRadarsError` (never retried). ``ble="best"`` picks the
    strongest signal. Either way, reconnects go to the radar found on the
    first connection.
    """
    from . import transport

    if reconnect is None:
        reconnect = ble is not None
    tk = tracker if tracker is not None else Tracker(**tracker_kwargs)
    delay = retry_delay
    while stop is None or not stop.is_set():
        try:
            opened = await _await_or_stop(
                transport.open_transport(port, baud, ble=ble), stop
            )
        except MultipleRadarsError:
            raise  # several radars found: retrying won't pick one
        except Exception as exc:
            if not reconnect:
                raise
            log.warning("connect failed (%s); retrying in %.0f s", exc, delay)
            await _sleep_or_stop(delay, stop)
            delay = min(delay * 2, max_retry_delay)
            continue
        if opened is None:  # stop fired while connecting
            return
        reader, writer = opened
        if ble in DISCOVERY_MODES and getattr(writer, "address", None):
            ble = writer.address  # reconnect to this radar, not whichever is first
        try:
            if enable_on_start:
                writer.write(enable_reporting())
                await writer.drain()
            async for report in iter_reports(
                reader, tk, clock=clock, read_size=read_size, stop=stop
            ):
                delay = retry_delay
                yield report
        except Exception as exc:
            if not reconnect:
                raise
            log.warning("connection error: %s", exc)
        finally:
            await _close(writer)
        if not reconnect or (stop is not None and stop.is_set()):
            return
        log.warning("disconnected; reconnecting in %.0f s", delay)
        await _sleep_or_stop(delay, stop)
        delay = min(delay * 2, max_retry_delay)
