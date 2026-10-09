from __future__ import annotations

import serial_asyncio


async def open_byte_stream(port: str, baud: int = 115200):
    """Open the serial port and return (reader, writer) asyncio streams.

    Returns asyncio StreamReader/StreamWriter; read bytes with
    `await reader.read(n)` and send command frames with `writer.write(...)`.
    """
    reader, writer = await serial_asyncio.open_serial_connection(
        url=port,
        baudrate=baud,
        bytesize=serial_asyncio.serial.EIGHTBITS,
        parity=serial_asyncio.serial.PARITY_NONE,
        stopbits=serial_asyncio.serial.STOPBITS_ONE,
    )
    return reader, writer


async def open_transport(port: str, baud: int = 115200, *, ble: str | None = None):
    """Open the serial port, or the BLE link when `ble` is given.

    `ble` is a MAC address or ``"auto"``; both paths return a (reader, writer)
    pair with the same read/write/drain/close/wait_closed interface.
    """
    if ble is not None:
        from .ble import open_ble_stream

        return await open_ble_stream(ble)
    return await open_byte_stream(port, baud)
