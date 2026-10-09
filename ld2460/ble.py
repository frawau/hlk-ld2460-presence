"""Bluetooth LE transport for the LD2460.

Over BLE the module is a transparent UART bridge: service FFF0 notifies the
same report/reply frames on FFF1 that the serial port emits, and command
frames written to FFF2 (write-without-response) reach the radar unchanged.
The link must be paired (LE Just Works) before the radar answers GATT
requests; `open_ble_stream` handles that on Linux/BlueZ.

Requires the optional dependency: ``pip install "hlk-ld2460-presence[ble]"``.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from dataclasses import dataclass

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"


def is_ld2460_name(name: str | None) -> bool:
    """True if an advertised name looks like an LD2460 (e.g. ``LD2460-6A62``)."""
    return bool(name) and "LD2460" in name


class BleByteStream:
    """Byte-stream view of a connected BleakClient.

    Acts as both the reader (``async read(n)``) consumed by `iter_reports` and
    the writer (``write`` / ``drain`` / ``close`` / ``wait_closed``) used for
    command frames, mirroring the asyncio stream pair the serial transport
    returns. A disconnect is reported as EOF (``b""``) once buffered data has
    been read.
    """

    def __init__(self, client, address: str | None = None) -> None:
        self._client = client
        self.address = address
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self._pending = b""
        self._eof = False
        self._writes: list[asyncio.Task] = []
        self._close_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._client.start_notify(NOTIFY_CHAR_UUID, self._on_notify)

    def _on_notify(self, _char, data: bytearray) -> None:
        self._chunks.put_nowait(bytes(data))

    def on_disconnect(self, _client) -> None:
        """bleak ``disconnected_callback``: wake the reader with EOF."""
        self._chunks.put_nowait(b"")

    async def read(self, n: int) -> bytes:
        if not self._pending:
            if self._eof:
                return b""
            chunk = await self._chunks.get()
            if not chunk:
                self._eof = True
                return b""
            self._pending = chunk
        out, self._pending = self._pending[:n], self._pending[n:]
        return out

    def write(self, data: bytes) -> None:
        self._writes.append(
            asyncio.ensure_future(
                self._client.write_gatt_char(WRITE_CHAR_UUID, data, response=False)
            )
        )

    async def drain(self) -> None:
        writes, self._writes = self._writes, []
        await asyncio.gather(*writes)

    def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.ensure_future(self._client.disconnect())
        self.on_disconnect(self._client)

    async def wait_closed(self) -> None:
        if self._close_task is not None:
            await self._close_task


@dataclass
class FoundRadar:
    """An LD2460 seen while scanning."""

    address: str
    name: str
    rssi: int
    device: object  # bleak BLEDevice


class MultipleRadarsError(LookupError):
    """Auto-discovery found more than one LD2460; the caller must pick one."""

    def __init__(self, radars: list[FoundRadar]) -> None:
        self.radars = radars
        listing = "".join(f"\n  {r.address}  {r.name}  {r.rssi} dBm" for r in radars)
        super().__init__(
            f"found {len(radars)} LD2460 radars; choose one with --ble ADDRESS:"
            + listing
        )


async def find_ld2460_devices(timeout: float = 6.0) -> list[FoundRadar]:
    """Scan for `timeout` seconds and return every advertising LD2460."""
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    radars = [
        FoundRadar(dev.address, adv.local_name or dev.name, adv.rssi, dev)
        for dev, adv in found.values()
        if is_ld2460_name(adv.local_name or dev.name)
    ]
    return sorted(radars, key=lambda r: r.rssi, reverse=True)


async def resolve_device(
    address: str, *, timeout: float = 20.0, scan_time: float = 6.0
):
    """Return the BLEDevice for a MAC address, or for the only LD2460 nearby.

    With ``"auto"`` the scan runs the full `scan_time` so every radar in range
    is seen: one radar is used, none raises ConnectionError, and several raise
    MultipleRadarsError listing them.
    """
    if address == "auto":
        radars = await find_ld2460_devices(min(scan_time, timeout))
        if not radars:
            raise ConnectionError("no LD2460 found while scanning")
        if len(radars) > 1:
            raise MultipleRadarsError(radars)
        return radars[0].device

    from bleak import BleakScanner

    device = await BleakScanner.find_device_by_address(address, timeout=timeout)
    if device is None:
        raise ConnectionError(f"LD2460 {address} not found while scanning")
    return device


async def open_ble_stream(
    address: str = "auto",
    *,
    pair: bool = True,
    timeout: float = 20.0,
):
    """Connect to an LD2460 over BLE and return ``(reader, writer)``.

    `address` is the MAC address, or ``"auto"`` for the only LD2460 in range
    (MultipleRadarsError if there are several). Pairing happens on the fly:
    with `pair` (default) on Linux, a temporary BlueZ agent accepts the Just
    Works pairing the radar demands; BlueZ keeps the bond afterwards, so later
    connections skip that step. Both returned objects are the same
    `BleByteStream`; its ``address`` is the MAC actually connected.
    """
    from bleak import BleakClient

    device = await resolve_device(address, timeout=timeout)

    agent = contextlib.nullcontext()
    if pair and sys.platform.startswith("linux"):
        from ._bluez_agent import JustWorksAgent

        agent = JustWorksAgent()

    stream: BleByteStream | None = None

    def _disconnected(client) -> None:
        if stream is not None:
            stream.on_disconnect(client)

    client = BleakClient(device, disconnected_callback=_disconnected, timeout=timeout)
    stream = BleByteStream(client, address=device.address)
    async with agent:
        await client.connect()
        try:
            if pair:
                await client.pair()
            await stream.start()
        except BaseException:
            await client.disconnect()
            raise
    return stream, stream
