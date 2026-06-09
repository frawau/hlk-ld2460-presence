# HLK-LD2460 Presence Decoder

Asyncio tool that decodes the Hi-Link HLK-LD2460 24 GHz radar serial stream and
reports presence, person count, and per-person motion (static / approaching /
moving away) to pluggable output sinks.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run

```bash
# Live text output on the default port /dev/ttyACM0
./venv/bin/python -m ld2460

# JSON lines, custom port, send the enable-reporting command on start
./venv/bin/python -m ld2460 --reporter json --port /dev/ttyACM0 --enable-on-start

# Both sinks at once
./venv/bin/python -m ld2460 --reporter text --reporter json
```

Options: `--port`, `--baud` (default 115200), `--reporter {text,json}`
(repeatable), `--static-threshold` (m/s dead-band for STATIC), `--gate` (max
metres a target may jump between frames), `--age-out` (seconds before an unseen
track is dropped), `--smoothing` (EMA factor in (0,1]; lower = steadier,
laggier), `--enable-on-start`.

## Use as a library

Drive the decoder from your own code (e.g. to feed another module) — no CLI
required. The simplest seam opens the port and yields `PresenceReport` objects:

```python
import asyncio
from ld2460 import stream_presence

async def main():
    async for report in stream_presence("/dev/ttyACM0", static_threshold=0.1):
        print(report.count, report.to_dict())

asyncio.run(main())
```

If you already manage the serial connection, use `iter_reports` with any object
exposing `async read(n) -> bytes`:

```python
from ld2460 import Tracker, iter_reports
from ld2460.transport import open_byte_stream

reader, _ = await open_byte_stream("/dev/ttyACM0")
async for report in iter_reports(reader, Tracker(smoothing=0.3)):
    ...  # report.present, report.count, report.persons[i].motion, .distance, .angle
```

Or push to multiple sinks with `run_pipeline(reader, tracker, reporters)` and
custom `Reporter` subclasses (see below). `PresenceReport.to_dict()` gives a
JSON-ready dict. Pass an `asyncio.Event` as `stop=` to any of these for
graceful shutdown.

## How motion is derived

The LD2460 protocol reports only target X/Y coordinates — no speed. This tool
tracks each target across frames and classifies motion from the change in its
radial distance from the sensor. Tune `--static-threshold` to trade jitter
against sensitivity.

## Adding an output sink

Subclass `ld2460.reporters.Reporter` (implement async `report()`; optional
`start()`/`close()`) and register it in `ld2460/__main__.py`. The core pipeline
is unchanged — this is the seam for an HTTP API or MQTT sink later.

## Hardware & datasheets

Sensor: **Hi-Link HLK-LD2460** — 24 GHz FMCW multi-target tracking radar
([product page](https://www.hlktech.net/index.php?id=1335)). Serial: 115200 8N1,
auto-reporting. The protocol decoded here is from Hi-Link's official documents:

- [HLK-LD2460 Serial Port Communication Protocol V1.0 (PDF)](https://drive.google.com/file/d/1ITkbJnLw8h1AQUSBlRK5ojEpac-IojdK/view)
- [HLK-LD2460 Module Manual V1.1 (PDF)](https://drive.google.com/file/d/1wIa3Xxt-dfxGxgpftlkIEOw1_iv_fVDZ/view)
- [All HLK-LD2460 resources (Google Drive folder, incl. Windows config tool)](https://drive.google.com/drive/folders/1JkImVaRfSgP8taq5W4aW_bCxlcqeHVan)

These PDFs are **not** committed to the repo (to avoid redistributing the
vendor's documents); download them from the links above into `docs/datasheets/`
for offline reference — see [`docs/datasheets/README.md`](docs/datasheets/README.md).
Wiring, board dimensions, pinout, and enclosure notes are in
[`docs/hardware-enclosure-notes.md`](docs/hardware-enclosure-notes.md).

## Tests

```bash
./venv/bin/pytest
```
