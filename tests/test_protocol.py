import struct

import pytest

from ld2460.protocol import (
    REPORT_HEADER,
    REPORT_TAIL,
    FrameError,
    _MAX_FRAME,
    build_report_frame,
    parse_report_frame,
)


def test_datasheet_example_single_target():
    # From HLK-LD2460 protocol V1.0: target at (1.5, 2.3)
    frame = bytes.fromhex("F4F3F2F1 04 0F00 0F00 1700 F8F7F6F5".replace(" ", ""))
    targets = parse_report_frame(frame)
    assert targets == [(1.5, 2.3)]


def test_zero_targets():
    frame = bytes.fromhex("F4F3F2F1 04 0B00 F8F7F6F5".replace(" ", ""))
    assert parse_report_frame(frame) == []


def test_multiple_and_negative_x():
    frame = build_report_frame([(-1.5, 2.0), (0.7, 4.2)])
    assert parse_report_frame(frame) == [(-1.5, 2.0), (0.7, 4.2)]


def test_build_matches_datasheet():
    assert build_report_frame([(1.5, 2.3)]).hex() == "f4f3f2f1040f000f001700f8f7f6f5"


def test_bad_header_raises():
    frame = bytes.fromhex("AABBCCDD 04 0B00 F8F7F6F5".replace(" ", ""))
    with pytest.raises(FrameError):
        parse_report_frame(frame)


def test_bad_tail_raises():
    frame = bytes.fromhex("F4F3F2F1 04 0B00 11223344".replace(" ", ""))
    with pytest.raises(FrameError):
        parse_report_frame(frame)


def test_length_mismatch_raises():
    frame = bytes.fromhex("F4F3F2F1 04 FF00 0F00 1700 F8F7F6F5".replace(" ", ""))
    with pytest.raises(FrameError):
        parse_report_frame(frame)


from ld2460.protocol import FrameReader


def test_framereader_single_frame():
    fr = FrameReader()
    frame = build_report_frame([(1.5, 2.3)])
    assert fr.feed(frame) == [[(1.5, 2.3)]]


def test_framereader_split_across_chunks():
    fr = FrameReader()
    frame = build_report_frame([(0.0, 2.0)])
    assert fr.feed(frame[:5]) == []
    assert fr.feed(frame[5:]) == [[(0.0, 2.0)]]


def test_framereader_resyncs_past_garbage():
    fr = FrameReader()
    frame = build_report_frame([(0.0, 2.0)])
    out = fr.feed(b"\x00\x11garbage" + frame)
    assert out == [[(0.0, 2.0)]]


def test_framereader_two_frames_in_one_feed():
    fr = FrameReader()
    a = build_report_frame([(1.0, 1.0)])
    b = build_report_frame([(2.0, 2.0), (3.0, 3.0)])
    assert fr.feed(a + b) == [[(1.0, 1.0)], [(2.0, 2.0), (3.0, 3.0)]]


def test_framereader_drops_frame_with_bad_tail():
    fr = FrameReader()
    good = build_report_frame([(0.0, 2.0)])
    bad = bytearray(build_report_frame([(0.0, 5.0)]))
    bad[-1] = 0x00  # corrupt tail
    out = fr.feed(bytes(bad) + good)
    assert out == [[(0.0, 2.0)]]


from ld2460.protocol import disable_reporting, enable_reporting, restart


def test_enable_reporting_bytes():
    assert enable_reporting().hex() == "fdfcfbfa060c0001" "04030201"


def test_disable_reporting_bytes():
    assert disable_reporting().hex() == "fdfcfbfa060c0000" "04030201"


def test_restart_bytes():
    assert restart().hex() == "fdfcfbfa0d0c0001" "04030201"


def test_framereader_rejects_oversized_length_immediately():
    # A false header claiming a huge (but >_MAX_FRAME) length must be skipped at
    # once, not buffered — the good frame right after it is returned without
    # waiting for the bogus byte count to arrive.
    good = build_report_frame([(0.0, 2.0)])
    false_header = REPORT_HEADER + bytes([0x04]) + (4095).to_bytes(2, "little")
    fr = FrameReader()
    out = fr.feed(false_header + good)
    assert out == [[(0.0, 2.0)]]


def test_framereader_split_mid_header():
    fr = FrameReader()
    frame = build_report_frame([(1.0, 2.0)])
    assert fr.feed(frame[:2]) == []  # only half the header
    assert fr.feed(frame[2:]) == [[(1.0, 2.0)]]


def test_framereader_two_bad_frames_then_good():
    fr = FrameReader()
    good = build_report_frame([(0.0, 2.0)])
    bad1 = bytearray(build_report_frame([(0.0, 5.0)]))
    bad1[-1] = 0x00  # corrupt tail
    bad2 = bytearray(build_report_frame([(1.0, 6.0)]))
    bad2[-1] = 0x00  # corrupt tail
    out = fr.feed(bytes(bad1) + bytes(bad2) + good)
    assert out == [[(0.0, 2.0)]]


def test_framereader_buffer_stays_bounded_under_garbage():
    # Flood with valid-looking headers + oversized lengths; buffer must not grow
    # without bound.
    fr = FrameReader()
    junk = (REPORT_HEADER + bytes([0x04]) + (4095).to_bytes(2, "little")) * 500
    fr.feed(junk)
    assert len(fr._buf) <= _MAX_FRAME + 8


def test_framereader_false_header_in_garbage_then_good():
    fr = FrameReader()
    good = build_report_frame([(2.0, 3.0)])
    # bytes that contain the header sequence mid-stream followed by junk then good
    out = fr.feed(b"\xff\xee" + REPORT_HEADER + b"\x04\x09\x00zzz" + good)
    assert out == [[(2.0, 3.0)]]
