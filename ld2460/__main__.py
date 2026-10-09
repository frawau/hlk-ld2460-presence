from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import socket
import time
from collections.abc import Sequence

from .app import deliver_reports, stream_presence
from .reporters import Reporter
from .reporters.console import ConsoleJsonReporter, ConsoleTextReporter
from .tracking import Tracker

_REPORTER_CHOICES = ["text", "json", "http"]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ld2460", description="HLK-LD2460 presence decoder"
    )
    p.add_argument("--port", default="/dev/ttyACM0", help="serial device")
    p.add_argument(
        "--ble",
        nargs="?",
        const="auto",
        default=None,
        metavar="ADDRESS",
        help="connect over Bluetooth LE instead of serial; ADDRESS is the radar's "
        "MAC, or omit it to use the first LD2460 found (needs the [ble] extra)",
    )
    p.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="baud rate (LD2460 default 115200; change only if you reconfigured the module)",
    )
    p.add_argument(
        "--no-reconnect",
        dest="reconnect",
        action="store_false",
        help="exit when the BLE link drops instead of reconnecting",
    )
    p.add_argument(
        "--reporter",
        action="append",
        choices=_REPORTER_CHOICES,
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
        "--server-url",
        default=None,
        help="dashboard server URL for --reporter http (e.g. http://localhost:8099)",
    )
    p.add_argument(
        "--screen-name",
        default=socket.gethostname(),
        help="screen name sent with --reporter http (default: hostname)",
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
    if "http" in args.reporter and not args.server_url:
        p.error("--reporter http requires --server-url")
    return args


def build_reporters(args: argparse.Namespace) -> list[Reporter]:
    out: list[Reporter] = []
    for name in args.reporter:
        if name == "text":
            out.append(ConsoleTextReporter())
        elif name == "json":
            out.append(ConsoleJsonReporter())
        elif name == "http":
            from .reporters.http_reporter import HttpReporter

            out.append(HttpReporter(args.server_url, args.screen_name))
    return out


def build_tracker(args: argparse.Namespace) -> Tracker:
    return Tracker(
        static_threshold=args.static_threshold,
        gate=args.gate,
        age_out=args.age_out,
        smoothing=args.smoothing,
    )


async def _amain(args: argparse.Namespace) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX
            pass

    reports = stream_presence(
        args.port,
        args.baud,
        ble=args.ble,
        reconnect=args.reconnect and args.ble is not None,
        tracker=build_tracker(args),
        enable_on_start=args.enable_on_start,
        stop=stop,
    )
    await deliver_reports(reports, build_reporters(args))


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%SZ"
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    _setup_logging()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
