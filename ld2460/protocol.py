from __future__ import annotations

import struct

REPORT_HEADER = bytes([0xF4, 0xF3, 0xF2, 0xF1])
REPORT_TAIL = bytes([0xF8, 0xF7, 0xF6, 0xF5])
REPORT_FUNC = 0x04

CMD_HEADER = bytes([0xFD, 0xFC, 0xFB, 0xFA])
CMD_TAIL = bytes([0x04, 0x03, 0x02, 0x01])

# Minimum report frame: header(4) + func(1) + length(2) + tail(4)
_REPORT_OVERHEAD = 11


class FrameError(ValueError):
    """Raised when a byte sequence is not a valid LD2460 report frame."""


def parse_report_frame(frame: bytes) -> list[tuple[float, float]]:
    """Decode a complete report frame into a list of (x, y) targets in metres."""
    if len(frame) < _REPORT_OVERHEAD:
        raise FrameError("frame too short")
    if frame[0:4] != REPORT_HEADER:
        raise FrameError("bad header")
    if frame[4] != REPORT_FUNC:
        raise FrameError("bad function code")
    length = int.from_bytes(frame[5:7], "little")
    if length != len(frame):
        raise FrameError(f"length mismatch: field={length} actual={len(frame)}")
    if (length - _REPORT_OVERHEAD) % 4 != 0:
        raise FrameError("invalid payload length")
    if frame[-4:] != REPORT_TAIL:
        raise FrameError("bad tail")
    n = (length - _REPORT_OVERHEAD) // 4
    targets: list[tuple[float, float]] = []
    offset = 7
    for _ in range(n):
        x_raw, y_raw = struct.unpack_from("<hh", frame, offset)
        targets.append((x_raw / 10.0, y_raw / 10.0))
        offset += 4
    return targets


def build_report_frame(targets: list[tuple[float, float]]) -> bytes:
    """Build a report frame from (x, y) metre coordinates (inverse of parse)."""
    body = b"".join(
        struct.pack("<hh", round(x * 10), round(y * 10)) for x, y in targets
    )
    length = _REPORT_OVERHEAD + len(body)
    return (
        REPORT_HEADER
        + bytes([REPORT_FUNC])
        + length.to_bytes(2, "little")
        + body
        + REPORT_TAIL
    )
