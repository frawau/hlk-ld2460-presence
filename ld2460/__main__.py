from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import socket
import sys
import time
from collections.abc import Sequence

from .app import deliver_reports, stream_presence
from .config import Mount, RadarConfig, RadarConfigurator, Sensitivity
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
    _add_config_parser(p.add_subparsers(dest="command", metavar="COMMAND"))
    argv = list(sys.argv[1:] if argv is None else argv)
    # `--ble config ...`: argparse would take "config" as the address.
    for i, arg in enumerate(argv[:-1]):
        if arg == "--ble" and argv[i + 1] == "config":
            argv.insert(i + 1, "auto")
            break
    args = p.parse_args(argv)
    if args.command == "config" and args.config_action == "set":
        if not config_changes(args):
            p.error("config set needs at least one setting to change")
    if not args.reporter:
        args.reporter = ["text"]
    if not 0.0 < args.smoothing <= 1.0:
        p.error("--smoothing must be in the range (0, 1]")
    if "http" in args.reporter and not args.server_url:
        p.error("--reporter http requires --server-url")
    return args


def _add_config_parser(sub) -> None:
    cfg = sub.add_parser(
        "config",
        help="show or change the radar's stored settings (works over --port or --ble)",
        description="Show or change the settings stored on the radar. Uses the "
        "connection chosen before the command: --port (serial, default) or --ble.",
    )
    actions = cfg.add_subparsers(dest="config_action", metavar="ACTION", required=True)

    show = actions.add_parser("show", help="print the current settings")
    show.add_argument("--json", action="store_true", help="print as JSON")

    st = actions.add_parser(
        "set",
        help="change settings; unspecified ones keep their stored value",
        description="Change settings; anything not given keeps its stored value. "
        "Wall mount: range 0–6 m, angles -60° to 60°, height 1.6–2.6 m, tilt 0–30°. "
        "Ceiling mount: range 0–4 m, angles 0° to 360°. Detection range is stored "
        "per mounting mode.",
    )
    st.add_argument("--mount", choices=[m.label for m in Mount], help="mounting mode")
    st.add_argument("--height", type=float, metavar="M", help="wall-mount height (m)")
    st.add_argument("--tilt", type=float, metavar="DEG", help="wall-mount tilt (°)")
    st.add_argument("--range", type=float, metavar="M", help="detection distance (m)")
    st.add_argument(
        "--angles",
        type=float,
        nargs=2,
        metavar=("START", "END"),
        help="detection angles (°), e.g. --angles -45 45",
    )
    st.add_argument(
        "--sensitivity", choices=[s.label for s in Sensitivity], help="sensitivity"
    )
    st.add_argument("--json", action="store_true", help="print the result as JSON")

    rs = actions.add_parser("reset", help="restore factory settings")
    rs.add_argument(
        "--yes", action="store_true", required=True, help="confirm the factory reset"
    )
    rs.add_argument("--json", action="store_true", help="print the result as JSON")


def config_changes(args: argparse.Namespace) -> dict:
    """Map `config set` arguments to RadarConfigurator.apply() keyword arguments."""
    out: dict = {}
    if args.mount is not None:
        out["mount"] = Mount[args.mount.upper()]
    if args.height is not None:
        out["height_m"] = args.height
    if args.tilt is not None:
        out["tilt_deg"] = args.tilt
    if args.range is not None:
        out["range_m"] = args.range
    if args.angles is not None:
        out["start_angle_deg"], out["end_angle_deg"] = args.angles
    if args.sensitivity is not None:
        out["sensitivity"] = Sensitivity[args.sensitivity.upper()]
    return out


def format_config(cfg: RadarConfig) -> str:
    lines = [
        f"Firmware:         {cfg.firmware}",
        f"Mount:            {cfg.mount.label}",
    ]
    if cfg.height_m is not None:
        lines.append(f"Height:           {cfg.height_m:.2f} m")
        lines.append(f"Tilt:             {cfg.tilt_deg:.1f}°")
    lines.append(
        f"Detection range:  {cfg.range_m:.1f} m, "
        f"{cfg.start_angle_deg:.1f}° to {cfg.end_angle_deg:.1f}°"
    )
    lines.append(f"Sensitivity:      {cfg.sensitivity.label}")
    return "\n".join(lines)


async def _config_main(args: argparse.Namespace) -> None:
    from .transport import open_transport

    reader, writer = await open_transport(args.port, args.baud, ble=args.ble)
    try:
        radar = RadarConfigurator(reader, writer)
        if args.config_action == "show":
            cfg = await radar.read_config()
        elif args.config_action == "set":
            cfg = await radar.apply(**config_changes(args))
        else:
            cfg = await radar.factory_reset()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # pragma: no cover - best-effort close
            pass
    print(json.dumps(cfg.to_dict()) if args.json else format_config(cfg))


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
    if args.command == "config":
        try:
            asyncio.run(_config_main(args))
        except (ValueError, TimeoutError, ConnectionError) as exc:
            # ConfigError is a ValueError: bad value or the radar refused it.
            raise SystemExit(f"ld2460 config: {exc}") from None
        return
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
