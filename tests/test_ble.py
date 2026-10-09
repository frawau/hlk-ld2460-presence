import asyncio

import pytest

from ld2460.app import iter_reports
from ld2460.ble import (
    NOTIFY_CHAR_UUID,
    WRITE_CHAR_UUID,
    BleByteStream,
    is_ld2460_name,
)
from ld2460.protocol import build_report_frame, enable_reporting
from ld2460.tracking import Tracker


class FakeClient:
    """Stands in for bleak.BleakClient: records calls, lets tests push notifies."""

    def __init__(self):
        self.notify_cb = None
        self.notify_uuid = None
        self.writes = []
        self.disconnected = False

    async def start_notify(self, uuid, callback):
        self.notify_uuid = uuid
        self.notify_cb = callback

    async def write_gatt_char(self, uuid, data, response=None):
        self.writes.append((uuid, bytes(data), response))

    async def disconnect(self):
        self.disconnected = True

    def push(self, data: bytes):
        self.notify_cb(None, bytearray(data))


async def _attached():
    client = FakeClient()
    stream = BleByteStream(client)
    await stream.start()
    return client, stream


async def test_start_subscribes_to_notify_characteristic():
    client, _ = await _attached()
    assert client.notify_uuid == NOTIFY_CHAR_UUID


async def test_notifications_are_returned_by_read():
    client, stream = await _attached()
    client.push(b"\x01\x02\x03")
    client.push(b"\x04")
    assert await stream.read(256) == b"\x01\x02\x03"
    assert await stream.read(256) == b"\x04"


async def test_read_honours_n_and_keeps_remainder():
    client, stream = await _attached()
    client.push(b"abcdef")
    assert await stream.read(4) == b"abcd"
    assert await stream.read(4) == b"ef"


async def test_read_blocks_until_data_arrives():
    client, stream = await _attached()
    task = asyncio.ensure_future(stream.read(256))
    await asyncio.sleep(0)
    assert not task.done()
    client.push(b"xy")
    assert await asyncio.wait_for(task, 1) == b"xy"


async def test_disconnect_signals_eof_after_buffered_data():
    client, stream = await _attached()
    client.push(b"last")
    stream.on_disconnect(None)
    assert await stream.read(256) == b"last"
    assert await stream.read(256) == b""
    assert await stream.read(256) == b""


async def test_write_uses_write_without_response():
    client, stream = await _attached()
    stream.write(enable_reporting())
    await stream.drain()
    assert client.writes == [(WRITE_CHAR_UUID, enable_reporting(), False)]


async def test_close_disconnects():
    client, stream = await _attached()
    stream.close()
    await stream.wait_closed()
    assert client.disconnected
    assert await stream.read(256) == b""


async def test_iter_reports_over_ble_stream():
    client, stream = await _attached()
    client.push(build_report_frame([(0.5, 2.0)]))
    # A command reply (detection-range query) interleaved with reports is skipped.
    client.push(bytes.fromhex("fdfcfbfa1210003ca8fd580204030201"))
    client.push(build_report_frame([]))
    stream.on_disconnect(None)
    reports = [r async for r in iter_reports(stream, Tracker())]
    assert [r.count for r in reports] == [1, 0]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("LD2460-6A62", True),
        ("HLK-LD2460", True),
        ("LD2450-1234", False),
        (None, False),
    ],
)
def test_is_ld2460_name(name, expected):
    assert is_ld2460_name(name) is expected


def _found(*macs):
    from ld2460.ble import FoundRadar

    return [
        FoundRadar(m, f"LD2460-{m[-5:].replace(':', '')}", -60, object()) for m in macs
    ]


async def test_auto_with_one_radar_picks_it(monkeypatch):
    import ld2460.ble as ble

    radars = _found("89:EC:12:F6:6A:62")

    async def fake_find(timeout):
        return radars

    monkeypatch.setattr(ble, "find_ld2460_devices", fake_find)
    assert await ble.resolve_device("auto", timeout=1) is radars[0].device


async def test_auto_with_several_radars_lists_them(monkeypatch):
    import ld2460.ble as ble

    radars = _found("89:EC:12:F6:6A:62", "89:EC:12:F6:11:22")

    async def fake_find(timeout):
        return radars

    monkeypatch.setattr(ble, "find_ld2460_devices", fake_find)
    with pytest.raises(ble.MultipleRadarsError) as err:
        await ble.resolve_device("auto", timeout=1)
    assert err.value.radars == radars
    assert "89:EC:12:F6:11:22" in str(err.value)


async def test_auto_with_no_radar_is_a_connection_error(monkeypatch):
    import ld2460.ble as ble

    async def fake_find(timeout):
        return []

    monkeypatch.setattr(ble, "find_ld2460_devices", fake_find)
    with pytest.raises(ConnectionError):
        await ble.resolve_device("auto", timeout=1)


async def test_best_picks_strongest_signal(monkeypatch):
    import ld2460.ble as ble

    weak, strong = _found("89:EC:12:F6:11:22", "89:EC:12:F6:6A:62")
    weak.rssi, strong.rssi = -85, -55

    async def fake_find(timeout):
        return [weak, strong]  # order must not matter

    monkeypatch.setattr(ble, "find_ld2460_devices", fake_find)
    assert await ble.resolve_device("best", timeout=1) is strong.device


async def test_best_with_no_radar_is_a_connection_error(monkeypatch):
    import ld2460.ble as ble

    async def fake_find(timeout):
        return []

    monkeypatch.setattr(ble, "find_ld2460_devices", fake_find)
    with pytest.raises(ConnectionError):
        await ble.resolve_device("best", timeout=1)
