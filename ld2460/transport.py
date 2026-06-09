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
