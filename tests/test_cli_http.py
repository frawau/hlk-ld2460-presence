import pytest

from ld2460.__main__ import build_reporters, parse_args


def test_http_reporter_needs_server_url():
    with pytest.raises(SystemExit):
        parse_args(["--reporter", "http"])  # no --server-url


def test_screen_name_defaults_to_hostname():
    import socket

    args = parse_args([])
    assert args.screen_name == socket.gethostname()


def test_build_http_reporter():
    pytest.importorskip("aiohttp")
    from ld2460.reporters.http_reporter import HttpReporter

    args = parse_args(
        ["--reporter", "http", "--server-url", "http://x:8099", "--screen-name", "lab"]
    )
    reporters = build_reporters(args)
    assert isinstance(reporters[0], HttpReporter)
