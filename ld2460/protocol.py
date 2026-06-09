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


# Header(4) + func(1) + length(2) before the payload.
_REPORT_PREFIX_LEN = len(REPORT_HEADER) + 1 + 2
# A report frame carries at most a handful of targets (the sensor tracks ~5
# people). Cap well above that so a corrupt length field is rejected
# immediately instead of stalling the reader while it waits for bogus bytes.
_MAX_TARGETS = 32
_MAX_FRAME = _MAX_TARGETS * 4 + _REPORT_OVERHEAD  # 139 bytes


class FrameReader:
    """Stateful, resynchronising parser. Feed raw bytes, get decoded frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[list[tuple[float, float]]]:
        self._buf.extend(data)
        frames: list[list[tuple[float, float]]] = []
        while True:
            frame = self._extract_one()
            if frame is None:
                break
            try:
                frames.append(parse_report_frame(frame))
            except FrameError:
                pass  # already resynced past the header in _extract_one
        return frames

    def _extract_one(self) -> bytes | None:
        while True:
            idx = self._buf.find(REPORT_HEADER)
            if idx == -1:
                # keep a possible partial header at the tail of the buffer
                partial = len(REPORT_HEADER) - 1
                if len(self._buf) > partial:
                    del self._buf[:-partial]
                return None
            if idx > 0:
                del self._buf[:idx]
            if len(self._buf) < _REPORT_PREFIX_LEN:
                return None  # need header + func + length
            length = int.from_bytes(self._buf[5:7], "little")
            if (
                length < _REPORT_OVERHEAD
                or length > _MAX_FRAME
                or (length - _REPORT_OVERHEAD) % 4 != 0
            ):
                del self._buf[:4]  # corrupt length — skip this header, resync
                continue
            if len(self._buf) < length:
                return None  # wait for the rest of the frame
            frame = bytes(self._buf[:length])
            if frame[-4:] != REPORT_TAIL:
                del self._buf[:4]  # bad tail — skip header, resync
                continue
            del self._buf[:length]
            return frame


def _command(func: int, data: bytes = b"") -> bytes:
    length = len(CMD_HEADER) + 1 + 2 + len(data) + len(CMD_TAIL)
    return CMD_HEADER + bytes([func]) + length.to_bytes(2, "little") + data + CMD_TAIL


def enable_reporting() -> bytes:
    return _command(0x06, b"\x01")


def disable_reporting() -> bytes:
    return _command(0x06, b"\x00")


def restart() -> bytes:
    return _command(0x0D, b"\x01")


__all__ = [
    "REPORT_HEADER",
    "REPORT_TAIL",
    "REPORT_FUNC",
    "CMD_HEADER",
    "CMD_TAIL",
    "FrameError",
    "parse_report_frame",
    "build_report_frame",
    "FrameReader",
    "enable_reporting",
    "disable_reporting",
    "restart",
]
