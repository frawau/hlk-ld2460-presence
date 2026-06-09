from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Sequence

from .app import run_pipeline
from .protocol import enable_reporting
from .reporters import Reporter
from .reporters.console import ConsoleJsonReporter, ConsoleTextReporter
from .tracking import Tracker
from .transport import open_byte_stream

_REPORTER_FACTORIES = {
    "text": ConsoleTextReporter,
    "json": ConsoleJsonReporter,
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ld2460", description="HLK-LD2460 presence decoder"
    )
    p.add_argument("--port", default="/dev/ttyACM0", help="serial device")
    p.add_argument("--baud", type=int, default=115200, help="baud rate")
    p.add_argument(
        "--reporter",
        action="append",
        choices=sorted(_REPORTER_FACTORIES),
        help="output sink (repeatable); default: text",
    )
    p.add_argument(
        "--static-threshold",
        type=float,
        default=0.05,
        help="radial speed (m/s) below which motion is STATIC",
    )
    p.add_argument(
        "--enable-on-start",
        action="store_true",
        help="send the enable-reporting command before listening",
    )
    args = p.parse_args(argv)
    if not args.reporter:
        args.reporter = ["text"]
    return args


def build_reporters(names: Sequence[str]) -> list[Reporter]:
    return [_REPORTER_FACTORIES[n]() for n in names]


async def _amain(args: argparse.Namespace) -> None:
    reader, writer = await open_byte_stream(args.port, args.baud)
    if args.enable_on_start:
        writer.write(enable_reporting())
        await writer.drain()
    tracker = Tracker(static_threshold=args.static_threshold)
    reporters = build_reporters(args.reporter)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX
            pass

    await run_pipeline(reader, tracker, reporters, stop=stop)


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(_amain(parse_args(argv)))


if __name__ == "__main__":
    main()
