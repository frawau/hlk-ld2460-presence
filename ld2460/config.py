"""Read and change the LD2460's stored settings.

Works over any transport (serial or BLE): the radar speaks the same command
protocol on both. Commands are re-sent until the matching reply arrives,
because the radar does not answer every request (notably over BLE).

Hi-Link's documents call the mounting modes "side" and "top"; this module
calls them wall and ceiling.
"""

from __future__ import annotations

import asyncio
import enum
from collections import deque
from dataclasses import dataclass

from . import protocol as p


class ConfigError(ValueError):
    """Rejected setting, or the radar reported that applying it failed."""


class Mount(enum.Enum):
    WALL = 0x01
    CEILING = 0x02

    @property
    def label(self) -> str:
        return self.name.lower()


class Sensitivity(enum.Enum):
    HIGH = 0x01
    MEDIUM = 0x02
    LOW = 0x03

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class RangeLimits:
    max_range_m: float
    min_angle_deg: float
    max_angle_deg: float


# Limits from the protocol document and the HLKRadarTool input checks.
RANGE_LIMITS = {
    Mount.WALL: RangeLimits(6.0, -60.0, 60.0),
    Mount.CEILING: RangeLimits(4.0, 0.0, 360.0),
}
HEIGHT_LIMITS_M = (1.6, 2.6)
TILT_LIMITS_DEG = (0.0, 30.0)


@dataclass
class RadarConfig:
    """Settings as stored on the radar. Height and tilt exist for wall mount only."""

    firmware: str
    mount: Mount
    height_m: float | None
    tilt_deg: float | None
    range_m: float
    start_angle_deg: float
    end_angle_deg: float
    sensitivity: Sensitivity

    def to_dict(self) -> dict:
        return {
            "firmware": self.firmware,
            "mount": self.mount.label,
            "height_m": self.height_m,
            "tilt_deg": self.tilt_deg,
            "range_m": self.range_m,
            "start_angle_deg": self.start_angle_deg,
            "end_angle_deg": self.end_angle_deg,
            "sensitivity": self.sensitivity.label,
        }


def _check(name: str, value: float, low: float, high: float, unit: str) -> None:
    if not low <= value <= high:
        raise ConfigError(f"{name} {value:g} {unit} is outside {low:g}–{high:g} {unit}")


def _check_range_values(
    mount: Mount,
    range_m: float | None,
    start: float | None,
    end: float | None,
) -> None:
    lim = RANGE_LIMITS[mount]
    if range_m is not None:
        if range_m <= 0:
            raise ConfigError("range must be greater than 0 m")
        _check(f"{mount.label} range", range_m, 0.0, lim.max_range_m, "m")
    for name, angle in (("start angle", start), ("end angle", end)):
        if angle is not None:
            _check(
                f"{mount.label} {name}",
                angle,
                lim.min_angle_deg,
                lim.max_angle_deg,
                "°",
            )
    if start is not None and end is not None and start >= end:
        raise ConfigError(
            f"start angle {start:g}° must be less than end angle {end:g}°"
        )


class RadarConfigurator:
    """Query and apply settings over an open (reader, writer) transport."""

    def __init__(self, reader, writer, *, retries: int = 15, interval: float = 0.3):
        self._reader = reader
        self._writer = writer
        self._retries = retries
        self._interval = interval
        self._replies = p.ReplyReader()
        self._pending: deque[tuple[int, bytes]] = deque()

    async def _request(self, frame: bytes) -> bytes:
        """Send `frame` until a reply with the same function code arrives."""
        func = frame[4]
        loop = asyncio.get_running_loop()
        for _ in range(self._retries):
            self._writer.write(frame)
            await self._writer.drain()
            deadline = loop.time() + self._interval
            while True:
                while self._pending:
                    got, data = self._pending.popleft()
                    if got == func:
                        return data
                left = deadline - loop.time()
                if left <= 0:
                    break
                try:
                    chunk = await asyncio.wait_for(self._reader.read(256), left)
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    raise ConnectionError("connection closed while configuring")
                self._pending.extend(self._replies.feed(chunk))
        raise TimeoutError(f"no reply from radar to command 0x{func:02X}")

    async def _set(self, frame: bytes, ok: bytes, what: str) -> None:
        reply = await self._request(frame)
        if reply[:1] != ok:
            raise ConfigError(f"radar rejected {what} (reply {reply.hex()})")

    async def read_config(self) -> RadarConfig:
        _, year, month, major, minor = p.decode_firmware(
            await self._request(p.query(p.FUNC_FIRMWARE))
        )
        mount = Mount((await self._request(p.query(p.FUNC_GET_MOUNT)))[0])
        height = tilt = None
        if mount is Mount.WALL:
            height, tilt = p.decode_installation(
                await self._request(p.query(p.FUNC_GET_INSTALLATION))
            )
        range_m, start, end = p.decode_detection_range(
            await self._request(p.query(p.FUNC_GET_RANGE))
        )
        sensitivity = Sensitivity(
            (await self._request(p.query(p.FUNC_GET_SENSITIVITY)))[0]
        )
        return RadarConfig(
            firmware=f"V{major}.{minor} ({year:04d}-{month:02d})",
            mount=mount,
            height_m=height,
            tilt_deg=tilt,
            range_m=range_m,
            start_angle_deg=start,
            end_angle_deg=end,
            sensitivity=sensitivity,
        )

    async def apply(
        self,
        *,
        mount: Mount | None = None,
        height_m: float | None = None,
        tilt_deg: float | None = None,
        range_m: float | None = None,
        start_angle_deg: float | None = None,
        end_angle_deg: float | None = None,
        sensitivity: Sensitivity | None = None,
    ) -> RadarConfig:
        """Change the given settings, leaving the others as stored.

        Every value is checked against the limits of the target mounting mode
        before anything is written. Values left out of a pair (height/tilt) or
        triple (range/start/end) keep their stored value. The detection range
        is stored per mounting mode, so after a mode change the missing parts
        come from the new mode's stored range. Returns the settings read back
        from the radar.
        """
        given = (
            mount,
            height_m,
            tilt_deg,
            range_m,
            start_angle_deg,
            end_angle_deg,
            sensitivity,
        )
        if all(v is None for v in given):
            raise ConfigError("no setting to change")

        current = await self.read_config()
        target = mount or current.mount
        installing = height_m is not None or tilt_deg is not None
        ranging = (
            range_m is not None
            or start_angle_deg is not None
            or end_angle_deg is not None
        )

        if installing:
            if target is not Mount.WALL:
                raise ConfigError("height and tilt can only be set for wall mount")
            if height_m is not None:
                _check("height", height_m, *HEIGHT_LIMITS_M, "m")
            if tilt_deg is not None:
                _check("tilt", tilt_deg, *TILT_LIMITS_DEG, "°")
        if ranging:
            _check_range_values(target, range_m, start_angle_deg, end_angle_deg)
            if target is current.mount:
                _check_range_values(
                    target,
                    None,
                    (
                        current.start_angle_deg
                        if start_angle_deg is None
                        else start_angle_deg
                    ),
                    current.end_angle_deg if end_angle_deg is None else end_angle_deg,
                )

        if target is not current.mount:
            # Reply: high nibble 1 = success, low nibble = mode.
            await self._set(
                p.set_mount(target.value), bytes([0x10 | target.value]), "mount"
            )
            current = await self.read_config()

        if installing:
            await self._set(
                p.set_installation(
                    current.height_m if height_m is None else height_m,
                    current.tilt_deg if tilt_deg is None else tilt_deg,
                ),
                b"\x01",
                "height/tilt",
            )
        if ranging:
            new_range = current.range_m if range_m is None else range_m
            start = (
                current.start_angle_deg if start_angle_deg is None else start_angle_deg
            )
            end = current.end_angle_deg if end_angle_deg is None else end_angle_deg
            _check_range_values(target, new_range, start, end)
            await self._set(
                p.set_detection_range(new_range, start, end), b"\x01", "detection range"
            )
        if sensitivity is not None:
            await self._set(
                p.set_sensitivity(sensitivity.value), b"\x01", "sensitivity"
            )
        return await self.read_config()

    async def factory_reset(self) -> RadarConfig:
        """Restore factory settings, then return them as read back."""
        await self._set(p.factory_reset(), b"\x01", "factory reset")
        return await self.read_config()
