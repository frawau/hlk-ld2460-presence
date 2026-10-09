import pytest

from ld2460.__main__ import build_reporters, build_tracker, parse_args
from ld2460.reporters.console import ConsoleJsonReporter, ConsoleTextReporter


def test_defaults():
    args = parse_args([])
    assert args.port == "/dev/ttyACM0"
    assert args.baud == 115200
    assert args.reporter == ["text"]
    assert args.enable_on_start is False


def test_reporter_selection():
    args = parse_args(["--reporter", "json", "--reporter", "text"])
    assert args.reporter == ["json", "text"]


def test_build_reporters_maps_names():
    args = parse_args(["--reporter", "text", "--reporter", "json"])
    reporters = build_reporters(args)
    assert isinstance(reporters[0], ConsoleTextReporter)
    assert isinstance(reporters[1], ConsoleJsonReporter)


def test_custom_port_and_threshold():
    args = parse_args(["--port", "/dev/ttyUSB0", "--static-threshold", "0.1"])
    assert args.port == "/dev/ttyUSB0"
    assert args.static_threshold == 0.1


def test_tracker_flags_parse():
    args = parse_args(["--gate", "2.0", "--age-out", "1.5", "--smoothing", "0.3"])
    assert args.gate == 2.0
    assert args.age_out == 1.5
    assert args.smoothing == 0.3


def test_build_tracker_threads_flags():
    args = parse_args(
        [
            "--gate",
            "2.0",
            "--age-out",
            "1.5",
            "--smoothing",
            "0.3",
            "--static-threshold",
            "0.2",
        ]
    )
    t = build_tracker(args)
    assert t.gate == 2.0
    assert t.age_out == 1.5
    assert t.smoothing == 0.3
    assert t.static_threshold == 0.2


def test_smoothing_out_of_range_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--smoothing", "1.5"])


def test_ble_defaults_off():
    assert parse_args([]).ble is None


def test_ble_without_value_means_auto():
    assert parse_args(["--ble"]).ble == "auto"


def test_ble_address():
    args = parse_args(["--ble", "89:EC:12:F6:6A:62"])
    assert args.ble == "89:EC:12:F6:6A:62"


def test_reconnect_on_by_default():
    assert parse_args(["--ble"]).reconnect is True


def test_no_reconnect_flag():
    assert parse_args(["--ble", "--no-reconnect"]).reconnect is False


def test_no_subcommand_runs_decoder():
    assert parse_args([]).command is None


def test_config_show_over_ble():
    args = parse_args(["--ble", "89:EC:12:F6:6A:62", "config", "show", "--json"])
    assert args.command == "config"
    assert args.config_action == "show"
    assert args.json is True
    assert args.ble == "89:EC:12:F6:6A:62"


def test_config_set_parses_metric_values_and_negative_angles():
    args = parse_args(
        [
            "--port",
            "/dev/ttyUSB0",
            "config",
            "set",
            "--mount",
            "wall",
            "--height",
            "2.2",
            "--tilt",
            "25",
            "--range",
            "4.5",
            "--angles",
            "-45",
            "45",
            "--sensitivity",
            "medium",
        ]
    )
    assert args.port == "/dev/ttyUSB0" and args.ble is None
    assert args.mount == "wall"
    assert (args.height, args.tilt, args.range) == (2.2, 25.0, 4.5)
    assert args.angles == [-45.0, 45.0]
    assert args.sensitivity == "medium"


def test_config_set_requires_a_setting():
    with pytest.raises(SystemExit):
        parse_args(["config", "set"])


def test_config_requires_action():
    with pytest.raises(SystemExit):
        parse_args(["config"])


def test_config_reset_requires_yes():
    with pytest.raises(SystemExit):
        parse_args(["config", "reset"])
    assert parse_args(["config", "reset", "--yes"]).config_action == "reset"


def test_config_kwargs_mapping():
    from ld2460.__main__ import config_changes
    from ld2460.config import Mount, Sensitivity

    args = parse_args(
        [
            "config",
            "set",
            "--mount",
            "ceiling",
            "--angles",
            "0",
            "270",
            "--sensitivity",
            "low",
        ]
    )
    assert config_changes(args) == {
        "mount": Mount.CEILING,
        "start_angle_deg": 0.0,
        "end_angle_deg": 270.0,
        "sensitivity": Sensitivity.LOW,
    }


def test_format_config_human_readable():
    from ld2460.__main__ import format_config
    from ld2460.config import Mount, RadarConfig, Sensitivity

    text = format_config(
        RadarConfig(
            "V1.3 (2025-03)", Mount.WALL, 2.6, 30.0, 6.0, -60.0, 60.0, Sensitivity.HIGH
        )
    )
    assert "Mount:            wall" in text
    assert "Height:           2.60 m" in text
    assert "Detection range:  6.0 m, -60.0° to 60.0°" in text


def test_bare_ble_before_config_means_auto():
    args = parse_args(["--ble", "config", "show"])
    assert args.ble == "auto"
    assert args.command == "config" and args.config_action == "show"


@pytest.mark.parametrize(
    "argv",
    [
        ["--port", "/dev/ttyUSB0", "--ble"],
        ["--ble", "89:EC:12:F6:6A:62", "--port", "/dev/ttyUSB0"],
        ["--ble", "--baud", "9600"],  # baud is serial-only
        ["--no-reconnect"],  # BLE-only
        ["--port", "/dev/ttyUSB0", "--no-reconnect"],
        ["--server-url", "http://x:8099"],  # needs --reporter http
        ["--screen-name", "hall"],
        ["--reporter", "json", "config", "show"],  # decoder-only with config
        ["--gate", "2", "config", "show"],
        ["--enable-on-start", "config", "show"],
        ["--ble", "--no-reconnect", "config", "show"],
    ],
)
def test_conflicting_options_rejected(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_serial_defaults_filled_when_not_using_ble():
    args = parse_args(["--baud", "230400"])
    assert (args.port, args.baud, args.ble) == ("/dev/ttyACM0", 230400, None)


def test_ble_leaves_serial_options_unset():
    args = parse_args(["--ble"])
    assert args.port is None and args.baud is None


def test_http_reporter_with_screen_name():
    args = parse_args(
        ["--reporter", "http", "--server-url", "http://x:8099", "--screen-name", "hall"]
    )
    assert (args.server_url, args.screen_name) == ("http://x:8099", "hall")


def test_config_over_serial_with_baud():
    args = parse_args(["--port", "/dev/ttyUSB0", "--baud", "9600", "config", "show"])
    assert (args.port, args.baud, args.command) == ("/dev/ttyUSB0", 9600, "config")


def test_main_lists_radars_and_exits(monkeypatch, capsys):
    import ld2460.__main__ as cli
    from ld2460.ble import FoundRadar, MultipleRadarsError

    async def fake_config_main(args):
        raise MultipleRadarsError(
            [
                FoundRadar("89:EC:12:F6:6A:62", "LD2460-6A62", -63, None),
                FoundRadar("89:EC:12:F6:11:22", "LD2460-1122", -80, None),
            ]
        )

    monkeypatch.setattr(cli, "_config_main", fake_config_main)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--ble", "config", "show"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "89:EC:12:F6:6A:62  LD2460-6A62  -63 dBm" in err
    assert "89:EC:12:F6:11:22  LD2460-1122  -80 dBm" in err
    assert "--ble ADDRESS" in err


def test_ble_best():
    assert parse_args(["--ble", "best"]).ble == "best"
    assert parse_args(["--ble", "best", "config", "show"]).ble == "best"
