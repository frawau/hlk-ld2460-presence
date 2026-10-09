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
