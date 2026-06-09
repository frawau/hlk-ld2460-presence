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
(repeatable), `--static-threshold` (m/s dead-band for STATIC),
`--enable-on-start`.

## How motion is derived

The LD2460 protocol reports only target X/Y coordinates — no speed. This tool
tracks each target across frames and classifies motion from the change in its
radial distance from the sensor. Tune `--static-threshold` to trade jitter
against sensitivity.

## Adding an output sink

Subclass `ld2460.reporters.Reporter` (implement async `report()`; optional
`start()`/`close()`) and register it in `ld2460/__main__.py`. The core pipeline
is unchanged — this is the seam for an HTTP API or MQTT sink later.

## Tests

```bash
./venv/bin/pytest
```
