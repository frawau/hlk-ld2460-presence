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
    reporters = build_reporters(["text", "json"])
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
