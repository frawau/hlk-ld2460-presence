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
    p.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="baud rate (LD2460 default 115200; change only if you reconfigured the module)",
    )
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
        "--gate",
        type=float,
        default=1.0,
        help="max metres a target may move between frames to stay the same track",
    )
    p.add_argument(
        "--age-out",
        type=float,
        default=0.5,
        help="seconds before an unseen track is dropped",
    )
    p.add_argument(
        "--smoothing",
        type=float,
        default=0.5,
        help="EMA factor in (0, 1] for distance/velocity (lower = steadier, laggier)",
    )
    p.add_argument(
        "--enable-on-start",
        action="store_true",
        help="send the enable-reporting command before listening",
    )
    args = p.parse_args(argv)
    if not args.reporter:
        args.reporter = ["text"]
    if not 0.0 < args.smoothing <= 1.0:
        p.error("--smoothing must be in the range (0, 1]")
    return args


def build_reporters(names: Sequence[str]) -> list[Reporter]:
    return [_REPORTER_FACTORIES[n]() for n in names]


def build_tracker(args: argparse.Namespace) -> Tracker:
    return Tracker(
        static_threshold=args.static_threshold,
        gate=args.gate,
        age_out=args.age_out,
        smoothing=args.smoothing,
    )


async def _amain(args: argparse.Namespace) -> None:
    reader, writer = await open_byte_stream(args.port, args.baud)
    try:
        if args.enable_on_start:
            writer.write(enable_reporting())
            await writer.drain()
        tracker = build_tracker(args)
        reporters = build_reporters(args.reporter)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # pragma: no cover - non-POSIX
                pass

        await run_pipeline(reader, tracker, reporters, stop=stop)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # pragma: no cover - best-effort close
            pass


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(_amain(parse_args(argv)))


if __name__ == "__main__":
    main()
