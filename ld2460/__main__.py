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
from .ble import MultipleRadarsError
from .config import Mount, RadarConfig, RadarConfigurator, Sensitivity
from .reporters import Reporter
from .reporters.console import ConsoleJsonReporter, ConsoleTextReporter
from .tracking import Tracker

_REPORTER_CHOICES = ["text", "json", "http"]


_DEFAULT_PORT = "/dev/ttyACM0"
_DEFAULT_BAUD = 115200

# Options that only affect the live decoder, not `config`. Each defaults to
# None so parse_args can tell whether it was given; real defaults are filled
# in afterwards.
_DECODER_DEFAULTS = {
    "reconnect": True,
    "enable_on_start": False,
    "static_threshold": 0.05,
    "gate": 1.0,
    "age_out": 0.5,
    "smoothing": 0.5,
    "reporter": ["text"],
    "server_url": None,
    "screen_name": None,  # filled in with the hostname
}


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ld2460",
        description="HLK-LD2460 presence decoder. Without a command, decodes the "
        "radar stream; `config` shows or changes the radar's settings.",
    )

    conn = p.add_argument_group(
        "connection", f"choose one; default: serial on {_DEFAULT_PORT}"
    )
    which = conn.add_mutually_exclusive_group()
    which.add_argument(
        "--port", metavar="DEVICE", help=f"serial device (default: {_DEFAULT_PORT})"
    )
    which.add_argument(
        "--ble",
        nargs="?",
        const="auto",
        metavar="ADDRESS",
        help="connect over Bluetooth LE, pairing on first use; ADDRESS is the "
        "radar's MAC, or omit it to use the only LD2460 in range (if several are "
        "found they are listed and ld2460 exits) (needs the [ble] extra)",
    )

    serial = p.add_argument_group("serial options")
    serial.add_argument(
        "--baud",
        type=int,
        help=f"baud rate (default: {_DEFAULT_BAUD}, the LD2460 factory setting)",
    )

    ble = p.add_argument_group("Bluetooth options (decoder only)")
    ble.add_argument(
        "--no-reconnect",
        dest="reconnect",
        action="store_const",
        const=False,
        help="exit when the BLE link drops instead of reconnecting",
    )

    radar = p.add_argument_group("radar (decoder only)")
    radar.add_argument(
        "--enable-on-start",
        action="store_const",
        const=True,
        help="send the enable-reporting command after connecting",
    )

    tracking = p.add_argument_group("tracking (decoder only)")
    tracking.add_argument(
        "--static-threshold",
        type=float,
        metavar="M_PER_S",
        help="radial speed below which motion is STATIC (default: 0.05)",
    )
    tracking.add_argument(
        "--gate",
        type=float,
        metavar="M",
        help="max distance a target may move between frames to stay the same "
        "track (default: 1.0)",
    )
    tracking.add_argument(
        "--age-out",
        type=float,
        metavar="S",
        help="seconds before an unseen track is dropped (default: 0.5)",
    )
    tracking.add_argument(
        "--smoothing",
        type=float,
        help="EMA factor in (0, 1] for distance/velocity; lower = steadier, "
        "laggier (default: 0.5)",
    )

    output = p.add_argument_group("output (decoder only)")
    output.add_argument(
        "--reporter",
        action="append",
        choices=_REPORTER_CHOICES,
        help="output sink, repeatable (default: text)",
    )
    output.add_argument(
        "--server-url",
        metavar="URL",
        help="dashboard server for --reporter http (e.g. http://localhost:8099)",
    )
    output.add_argument(
        "--screen-name",
        metavar="NAME",
        help="screen name sent with --reporter http (default: hostname)",
    )

    _add_config_parser(p.add_subparsers(dest="command", metavar="[COMMAND]"))
    argv = list(sys.argv[1:] if argv is None else argv)
    # `--ble config ...`: argparse would take "config" as the address.
    for i, arg in enumerate(argv[:-1]):
        if arg == "--ble" and argv[i + 1] == "config":
            argv.insert(i + 1, "auto")
            break
    args = p.parse_args(argv)
    _check_combinations(p, args)
    _fill_defaults(args)
    return args


def _check_combinations(p: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.ble is not None and args.baud is not None:
        p.error("--baud only applies to a serial connection, not --ble")
    if args.command == "config":
        given = [_flag(k) for k in _DECODER_DEFAULTS if getattr(args, k) is not None]
        if given:
            verb = "applies" if len(given) == 1 else "apply"
            p.error(f"{', '.join(given)} only {verb} to the decoder, not config")
        if args.config_action == "set" and not config_changes(args):
            p.error("config set needs at least one setting to change")
        return
    if args.reconnect is not None and args.ble is None:
        p.error("--no-reconnect only applies to --ble")
    if args.smoothing is not None and not 0.0 < args.smoothing <= 1.0:
        p.error("--smoothing must be in the range (0, 1]")
    if "http" in (args.reporter or []):
        if not args.server_url:
            p.error("--reporter http requires --server-url")
    else:
        for name in ("server_url", "screen_name"):
            if getattr(args, name) is not None:
                p.error(f"{_flag(name)} only applies with --reporter http")


def _fill_defaults(args: argparse.Namespace) -> None:
    if args.ble is None:
        args.port = args.port or _DEFAULT_PORT
        args.baud = args.baud or _DEFAULT_BAUD
    for name, default in _DECODER_DEFAULTS.items():
        if getattr(args, name) is None:
            setattr(args, name, default)
    if args.screen_name is None:
        args.screen_name = socket.gethostname()


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
    try:
        if args.command == "config":
            try:
                asyncio.run(_config_main(args))
            except (ValueError, TimeoutError, ConnectionError) as exc:
                # ConfigError is a ValueError: bad value or the radar refused it.
                raise SystemExit(f"ld2460 config: {exc}") from None
            return
        asyncio.run(_amain(args))
    except MultipleRadarsError as exc:  # --ble with several radars in range
        print(f"ld2460: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
