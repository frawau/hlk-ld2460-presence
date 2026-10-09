"""Configuration command frames and replies (HLK-LD2460 protocol V1.0 §4–16)."""

from ld2460.protocol import (
    ReplyReader,
    build_report_frame,
    decode_detection_range,
    decode_firmware,
    decode_installation,
    factory_reset,
    query,
    set_detection_range,
    set_installation,
    set_mount,
    set_sensitivity,
)


def h(s: str) -> bytes:
    return bytes.fromhex(s.replace(" ", ""))


def test_query_detection_range_matches_datasheet():
    assert query(0x12) == h("FD FC FB FA 12 0C 00 01 04 03 02 01")


def test_set_installation_matches_datasheet():
    # 2.6 m, 30°
    assert set_installation(2.6, 30.0) == h(
        "FD FC FB FA 07 0F 00 04 01 B8 0B 04 03 02 01"
    )


def test_set_detection_range_matches_datasheet():
    # 6 m, ±50°
    assert set_detection_range(6.0, -50.0, 50.0) == h(
        "FD FC FB FA 11 10 00 3C 0C FE F4 01 04 03 02 01"
    )


def test_set_mount_wall_matches_datasheet():
    assert set_mount(0x01) == h("FD FC FB FA 09 0C 00 01 04 03 02 01")


def test_set_sensitivity_high_matches_datasheet():
    assert set_sensitivity(0x01) == h("FD FC FB FA 13 0C 00 01 04 03 02 01")


def test_factory_reset_matches_datasheet():
    assert factory_reset() == h("FD FC FB FA 10 0C 00 01 04 03 02 01")


def test_decode_detection_range():
    assert decode_detection_range(h("3C 0C FE F4 01")) == (6.0, -50.0, 50.0)


def test_decode_installation():
    assert decode_installation(h("04 01 B8 0B")) == (2.6, 30.0)


def test_decode_firmware():
    # V1.2, February 2025, top-mount firmware
    assert decode_firmware(h("02 19 02 01 02")) == (2, 2025, 2, 1, 2)


def test_reply_reader_single_reply():
    rr = ReplyReader()
    assert rr.feed(h("FD FC FB FA 14 0C 00 02 04 03 02 01")) == [(0x14, b"\x02")]


def test_reply_reader_split_and_interleaved_with_reports():
    reply = h("FD FC FB FA 12 10 00 3C A8 FD 58 02 04 03 02 01")
    stream = build_report_frame([(1.0, 2.0)]) + reply + build_report_frame([])
    rr = ReplyReader()
    out = []
    for i in range(0, len(stream), 5):
        out += rr.feed(stream[i : i + 5])
    assert out == [(0x12, h("3C A8 FD 58 02"))]


def test_reply_reader_resyncs_past_garbage_and_bad_tail():
    bad = h("FD FC FB FA 0A 0C 00 01 00 00 00 00")
    good = h("FD FC FB FA 0A 0C 00 02 04 03 02 01")
    rr = ReplyReader()
    assert rr.feed(b"\x00\xfd\x11" + bad + good) == [(0x0A, b"\x02")]
