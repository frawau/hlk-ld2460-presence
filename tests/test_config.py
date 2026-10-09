import asyncio

import pytest

from ld2460.config import (
    ConfigError,
    Mount,
    RadarConfigurator,
    Sensitivity,
)
from ld2460.protocol import CMD_HEADER, CMD_TAIL, build_report_frame


def _reply(func: int, data: bytes) -> bytes:
    length = len(CMD_HEADER) + 1 + 2 + len(data) + len(CMD_TAIL)
    return CMD_HEADER + bytes([func]) + length.to_bytes(2, "little") + data + CMD_TAIL


class FakeRadar:
    """Simulates the LD2460 command interface over a reader/writer pair.

    Starts at factory settings. `drop` ignores that many incoming commands
    (lost writes); `silent` never answers; `fail` answers set commands with
    the failure code; `noise` interleaves a report frame before each reply.
    """

    def __init__(self, *, drop=0, silent=False, fail=False, noise=True):
        self._factory_settings()
        self.drop = drop
        self.silent = silent
        self.fail = fail
        self.noise = noise
        self.commands: list[tuple[int, bytes]] = []
        self._out: asyncio.Queue[bytes] = asyncio.Queue()

    def _factory_settings(self):
        self.mount = 1
        self.height = 260
        self.tilt = 3000
        self.ranges = {1: (60, -600, 600), 2: (40, 0, 3600)}
        self.sensitivity = 1

    # reader side
    async def read(self, _n):
        return await self._out.get()

    # writer side
    def write(self, frame: bytes):
        func, data = frame[4], frame[7:-4]
        self.commands.append((func, data))
        if self.silent:
            return
        if self.drop:
            self.drop -= 1
            return
        reply = self._handle(func, data)
        if self.noise:
            self._out.put_nowait(build_report_frame([(0.5, 1.5)]))
        self._out.put_nowait(_reply(func, reply))

    async def drain(self):
        pass

    def _handle(self, func, data):
        ok = b"\x00" if self.fail else b"\x01"
        if func == 0x0B:
            return bytes([self.mount, 25, 3, 1, 3])
        if func == 0x0A:
            return bytes([self.mount])
        if func == 0x08:
            return self.height.to_bytes(2, "little") + self.tilt.to_bytes(2, "little")
        if func == 0x12:
            d, s, e = self.ranges[self.mount]
            return (
                bytes([d])
                + s.to_bytes(2, "little", signed=True)
                + e.to_bytes(2, "little", signed=True)
            )
        if func == 0x14:
            return bytes([self.sensitivity])
        if func == 0x09:
            if self.fail:
                return bytes([data[0]])
            self.mount = data[0]
            return bytes([0x10 | data[0]])
        if func == 0x07:
            if not self.fail:
                self.height = int.from_bytes(data[0:2], "little")
                self.tilt = int.from_bytes(data[2:4], "little")
            return ok
        if func == 0x11:
            if not self.fail:
                self.ranges[self.mount] = (
                    data[0],
                    int.from_bytes(data[1:3], "little", signed=True),
                    int.from_bytes(data[3:5], "little", signed=True),
                )
            return ok
        if func == 0x13:
            if not self.fail:
                self.sensitivity = data[0]
            return ok
        if func == 0x10:
            self._factory_settings()
            return b"\x01"
        raise AssertionError(f"unexpected command 0x{func:02X}")

    def sets(self):
        return [f for f, _ in self.commands if f in (0x07, 0x09, 0x10, 0x11, 0x13)]


def _cfg(radar, **kw):
    kw.setdefault("interval", 0.02)
    return RadarConfigurator(radar, radar, **kw)


async def test_read_config_wall():
    cfg = await _cfg(FakeRadar()).read_config()
    assert cfg.firmware == "V1.3 (2025-03)"
    assert cfg.mount is Mount.WALL
    assert (cfg.height_m, cfg.tilt_deg) == (2.6, 30.0)
    assert (cfg.range_m, cfg.start_angle_deg, cfg.end_angle_deg) == (6.0, -60.0, 60.0)
    assert cfg.sensitivity is Sensitivity.HIGH


async def test_read_config_ceiling_skips_installation_query():
    radar = FakeRadar()
    radar.mount = 2
    cfg = await _cfg(radar).read_config()
    assert cfg.mount is Mount.CEILING
    assert cfg.height_m is None and cfg.tilt_deg is None
    assert (cfg.range_m, cfg.start_angle_deg, cfg.end_angle_deg) == (4.0, 0.0, 360.0)
    assert 0x08 not in [f for f, _ in radar.commands]


async def test_to_dict_is_metric_and_json_ready():
    d = (await _cfg(FakeRadar()).read_config()).to_dict()
    assert d == {
        "firmware": "V1.3 (2025-03)",
        "mount": "wall",
        "height_m": 2.6,
        "tilt_deg": 30.0,
        "range_m": 6.0,
        "start_angle_deg": -60.0,
        "end_angle_deg": 60.0,
        "sensitivity": "high",
    }


async def test_lost_commands_are_retried():
    radar = FakeRadar(drop=3)
    cfg = await _cfg(radar).read_config()
    assert cfg.mount is Mount.WALL
    assert [f for f, _ in radar.commands][:4] == [0x0B] * 4


async def test_no_reply_times_out():
    with pytest.raises(TimeoutError):
        await _cfg(FakeRadar(silent=True), retries=3).read_config()


async def test_closed_connection_raises():
    class Closed(FakeRadar):
        async def read(self, _n):
            return b""

    with pytest.raises(ConnectionError):
        await _cfg(Closed(silent=True)).read_config()


async def test_set_range_only_keeps_current_angles():
    radar = FakeRadar()
    cfg = await _cfg(radar).apply(range_m=4.5)
    assert radar.ranges[1] == (45, -600, 600)
    assert (cfg.range_m, cfg.start_angle_deg, cfg.end_angle_deg) == (4.5, -60.0, 60.0)


async def test_set_angles_only_keeps_current_range():
    radar = FakeRadar()
    await _cfg(radar).apply(start_angle_deg=-45, end_angle_deg=30)
    assert radar.ranges[1] == (60, -450, 300)


async def test_set_height_and_tilt():
    radar = FakeRadar()
    cfg = await _cfg(radar).apply(height_m=2.2, tilt_deg=25)
    assert (radar.height, radar.tilt) == (220, 2500)
    assert (cfg.height_m, cfg.tilt_deg) == (2.2, 25.0)


async def test_set_tilt_only_keeps_height():
    radar = FakeRadar()
    await _cfg(radar).apply(tilt_deg=20)
    assert (radar.height, radar.tilt) == (260, 2000)


async def test_switch_to_ceiling_then_set_ceiling_range():
    radar = FakeRadar()
    cfg = await _cfg(radar).apply(
        mount=Mount.CEILING, range_m=3.5, start_angle_deg=0, end_angle_deg=270
    )
    assert radar.mount == 2
    assert radar.ranges[2] == (35, 0, 2700)
    assert radar.ranges[1] == (60, -600, 600)  # wall range untouched
    assert cfg.mount is Mount.CEILING and cfg.range_m == 3.5


async def test_set_sensitivity():
    radar = FakeRadar()
    cfg = await _cfg(radar).apply(sensitivity=Sensitivity.LOW)
    assert radar.sensitivity == 3 and cfg.sensitivity is Sensitivity.LOW


@pytest.mark.parametrize(
    "kwargs",
    [
        {"range_m": 6.5},  # wall max 6 m
        {"range_m": 0},
        {"start_angle_deg": -70},  # wall ±60°
        {"start_angle_deg": 40, "end_angle_deg": 10},  # start after end
        {"height_m": 3.0},  # 1.6–2.6 m
        {"tilt_deg": 31},  # 0–30°
        {"mount": Mount.CEILING, "range_m": 5.0},  # ceiling max 4 m
        {"mount": Mount.CEILING, "height_m": 2.0},  # wall only
    ],
)
async def test_invalid_values_rejected_before_any_write(kwargs):
    radar = FakeRadar()
    with pytest.raises(ConfigError):
        await _cfg(radar).apply(**kwargs)
    assert radar.sets() == []


async def test_height_rejected_when_already_ceiling():
    radar = FakeRadar()
    radar.mount = 2
    with pytest.raises(ConfigError):
        await _cfg(radar).apply(tilt_deg=10)
    assert radar.sets() == []


async def test_partial_ceiling_angle_checked_against_stored_range():
    radar = FakeRadar()
    radar.mount = 2  # stored ceiling range 0–360°
    with pytest.raises(ConfigError):
        await _cfg(radar).apply(start_angle_deg=360)  # not before end 360
    assert radar.sets() == []


async def test_radar_failure_code_raises():
    with pytest.raises(ConfigError):
        await _cfg(FakeRadar(fail=True)).apply(range_m=5.0)


async def test_no_changes_is_rejected():
    with pytest.raises(ConfigError):
        await _cfg(FakeRadar()).apply()


async def test_factory_reset():
    radar = FakeRadar()
    radar.sensitivity = 3
    cfg = await _cfg(radar).factory_reset()
    assert cfg.sensitivity is Sensitivity.HIGH
    assert 0x10 in radar.sets()


class SerialLikeRadar(FakeRadar):
    """Serial delivers arbitrary byte fragments, not one frame per read."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._bytes = bytearray()

    async def read(self, n):
        while not self._bytes:
            self._bytes.extend(await self._out.get())
        out = bytes(self._bytes[: min(n, 3)])
        del self._bytes[: len(out)]
        return out


async def test_config_over_fragmented_serial_stream():
    radar = SerialLikeRadar()
    cfg = await _cfg(radar).apply(range_m=5.0, start_angle_deg=-30, end_angle_deg=30)
    assert radar.ranges[1] == (50, -300, 300)
    assert (cfg.range_m, cfg.start_angle_deg, cfg.end_angle_deg) == (5.0, -30.0, 30.0)
