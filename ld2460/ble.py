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

    def __init__(self, client) -> None:
        self._client = client
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


async def find_ld2460(timeout: float = 10.0):
    """Scan and return the first advertising LD2460 BLEDevice, or None."""
    from bleak import BleakScanner

    return await BleakScanner.find_device_by_filter(
        lambda dev, adv: is_ld2460_name(adv.local_name or dev.name),
        timeout=timeout,
    )


async def open_ble_stream(
    address: str = "auto",
    *,
    pair: bool = True,
    timeout: float = 20.0,
):
    """Connect to an LD2460 over BLE and return ``(reader, writer)``.

    `address` is the MAC address, or ``"auto"`` for the first LD2460 found by
    scanning. With `pair` (default) on Linux, a temporary BlueZ agent accepts
    the Just Works pairing the radar demands; once bonded, later connections
    reuse the stored keys. Both returned objects are the same `BleByteStream`.
    """
    from bleak import BleakClient, BleakScanner

    if address == "auto":
        device = await find_ld2460(timeout)
        if device is None:
            raise ConnectionError("no LD2460 found while scanning")
    else:
        device = await BleakScanner.find_device_by_address(address, timeout=timeout)
        if device is None:
            raise ConnectionError(f"LD2460 {address} not found while scanning")

    agent = contextlib.nullcontext()
    if pair and sys.platform.startswith("linux"):
        from ._bluez_agent import JustWorksAgent

        agent = JustWorksAgent()

    stream: BleByteStream | None = None

    def _disconnected(client) -> None:
        if stream is not None:
            stream.on_disconnect(client)

    client = BleakClient(device, disconnected_callback=_disconnected, timeout=timeout)
    stream = BleByteStream(client)
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
