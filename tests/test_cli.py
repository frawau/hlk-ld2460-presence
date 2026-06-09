from ld2460.__main__ import build_reporters, parse_args
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
