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
