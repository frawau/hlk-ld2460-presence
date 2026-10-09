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
        return _extract_frame(
            self._buf, REPORT_HEADER, REPORT_TAIL, _valid_report_length
        )


def _valid_report_length(length: int) -> bool:
    return (
        _REPORT_OVERHEAD <= length <= _MAX_FRAME
        and (length - _REPORT_OVERHEAD) % 4 == 0
    )


def _extract_frame(buf: bytearray, header: bytes, tail: bytes, valid_length):
    """Pop the next complete header…tail frame off `buf`, resyncing on junk.

    Returns the frame bytes, or None when more data is needed. Bytes before a
    header are discarded; a header with an implausible length or a bad tail is
    skipped so parsing resumes at the next header.
    """
    prefix_len = len(header) + 1 + 2  # header + func + length
    while True:
        idx = buf.find(header)
        if idx == -1:
            # keep a possible partial header at the tail of the buffer
            partial = len(header) - 1
            if len(buf) > partial:
                del buf[:-partial]
            return None
        if idx > 0:
            del buf[:idx]
        if len(buf) < prefix_len:
            return None  # need header + func + length
        length = int.from_bytes(buf[5:7], "little")
        if not valid_length(length):
            del buf[: len(header)]  # corrupt length — skip this header, resync
            continue
        if len(buf) < length:
            return None  # wait for the rest of the frame
        frame = bytes(buf[:length])
        if frame[-len(tail) :] != tail:
            del buf[: len(header)]  # bad tail — skip header, resync
            continue
        del buf[:length]
        return frame


# Command replies carry at most 5 data bytes; cap generously.
_CMD_OVERHEAD = len(CMD_HEADER) + 1 + 2 + len(CMD_TAIL)
_MAX_CMD_FRAME = 64


class ReplyReader:
    """Stateful parser for command replies (FD FC FB FA … 04 03 02 01).

    Feed raw bytes from the radar; report frames and junk in between are
    skipped. Returns ``(function_code, data)`` tuples.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self._buf.extend(data)
        replies: list[tuple[int, bytes]] = []
        while True:
            frame = _extract_frame(
                self._buf,
                CMD_HEADER,
                CMD_TAIL,
                lambda n: _CMD_OVERHEAD <= n <= _MAX_CMD_FRAME,
            )
            if frame is None:
                return replies
            replies.append((frame[4], frame[7 : -len(CMD_TAIL)]))


def _command(func: int, data: bytes = b"") -> bytes:
    length = len(CMD_HEADER) + 1 + 2 + len(data) + len(CMD_TAIL)
    return CMD_HEADER + bytes([func]) + length.to_bytes(2, "little") + data + CMD_TAIL


def enable_reporting() -> bytes:
    return _command(0x06, b"\x01")


def disable_reporting() -> bytes:
    return _command(0x06, b"\x00")


def restart() -> bytes:
    return _command(0x0D, b"\x01")


# Function codes of the configuration commands (protocol V1.0 §4–16).
FUNC_REPORTING = 0x06
FUNC_SET_INSTALLATION = 0x07
FUNC_GET_INSTALLATION = 0x08
FUNC_SET_MOUNT = 0x09
FUNC_GET_MOUNT = 0x0A
FUNC_FIRMWARE = 0x0B
FUNC_RESTART = 0x0D
FUNC_FACTORY_RESET = 0x10
FUNC_SET_RANGE = 0x11
FUNC_GET_RANGE = 0x12
FUNC_SET_SENSITIVITY = 0x13
FUNC_GET_SENSITIVITY = 0x14


def query(func: int) -> bytes:
    """Query command: every LD2460 query carries the single data byte 0x01."""
    return _command(func, b"\x01")


def set_mount(code: int) -> bytes:
    """0x01 = wall (Hi-Link: "side") mount, 0x02 = ceiling ("top") mount."""
    return _command(FUNC_SET_MOUNT, bytes([code]))


def set_installation(height_m: float, tilt_deg: float) -> bytes:
    """Wall-mount height (m) and tilt (°), sent as 0.01 units."""
    return _command(
        FUNC_SET_INSTALLATION,
        struct.pack("<HH", round(height_m * 100), round(tilt_deg * 100)),
    )


def set_detection_range(distance_m: float, start_deg: float, end_deg: float) -> bytes:
    """Detection distance (0.1 m, one byte) and start/end angle (0.1°, int16)."""
    return _command(
        FUNC_SET_RANGE,
        bytes([round(distance_m * 10)])
        + struct.pack("<hh", round(start_deg * 10), round(end_deg * 10)),
    )


def set_sensitivity(code: int) -> bytes:
    """0x01 = high, 0x02 = medium, 0x03 = low."""
    return _command(FUNC_SET_SENSITIVITY, bytes([code]))


def factory_reset() -> bytes:
    return _command(FUNC_FACTORY_RESET, b"\x01")


def decode_installation(data: bytes) -> tuple[float, float]:
    """Reply to 0x08 → (height m, tilt °)."""
    height, tilt = struct.unpack_from("<HH", data)
    return height / 100.0, tilt / 100.0


def decode_detection_range(data: bytes) -> tuple[float, float, float]:
    """Reply to 0x12 → (distance m, start angle °, end angle °)."""
    start, end = struct.unpack_from("<hh", data, 1)
    return data[0] / 10.0, start / 10.0, end / 10.0


def decode_firmware(data: bytes) -> tuple[int, int, int, int, int]:
    """Reply to 0x0B → (mount variant, year, month, major, minor)."""
    variant, year, month, major, minor = data[:5]
    return variant, 2000 + year, month, major, minor


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
    "ReplyReader",
    "query",
    "set_mount",
    "set_installation",
    "set_detection_range",
    "set_sensitivity",
    "factory_reset",
    "decode_installation",
    "decode_detection_range",
    "decode_firmware",
    "enable_reporting",
    "disable_reporting",
    "restart",
]
