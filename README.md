# HLK-LD2460 Presence Decoder

Asyncio tool that decodes the Hi-Link HLK-LD2460 24 GHz radar serial stream and
reports presence, person count, and per-person motion (static / approaching /
moving away) to pluggable output sinks.

## Install

```bash
# From a clone (editable install, recommended for development)
python3 -m venv venv
./venv/bin/pip install -e .          # add ".[test]" to also get pytest

# Or straight from GitHub
pip install git+https://github.com/frawau/hlk-ld2460-presence.git
```

This installs the importable `ld2460` library and the `ld2460` console command
(dependencies `pyserial` + `pyserial-asyncio` come with it).

## Run

```bash
# Live text output on the default port /dev/ttyACM0
ld2460

# JSON lines, custom port, send the enable-reporting command on start
ld2460 --reporter json --port /dev/ttyACM0 --enable-on-start

# Both sinks at once
ld2460 --reporter text --reporter json
```

(If you didn't install it, the equivalent is `python -m ld2460 ...`.)

Options (`ld2460 --help` shows them grouped):

- **Connection**, pick one: `--port DEVICE` (serial, default `/dev/ttyACM0`)
  or `--ble [ADDRESS]` (Bluetooth LE, see below). Passing both is an error.
- **Serial only:** `--baud` (default 115200).
- **BLE only:** `--no-reconnect`.
- **Decoder only** (not with `config`): `--enable-on-start`; tracking
  `--static-threshold` (m/s dead-band for STATIC), `--gate` (max metres a
  target may jump between frames), `--age-out` (seconds before an unseen track
  is dropped), `--smoothing` (EMA factor in (0,1]; lower = steadier, laggier);
  output `--reporter {text,json,http}` (repeatable), and `--server-url` /
  `--screen-name`, which only apply with `--reporter http`.

Options that don't fit the chosen connection or command are rejected rather
than silently ignored.

## Bluetooth LE (optional)

The LD2460 also streams over BLE, so it can run without a USB/UART cable.
Install the extra and pass `--ble`:

```bash
pip install -e ".[ble]"              # adds bleak

ld2460 --ble                         # the only LD2460 in range
ld2460 --ble best                    # the LD2460 with the strongest signal
ld2460 --ble 89:EC:12:F6:6A:62       # a specific radar
```

Nothing needs to be set up beforehand: `--ble` scans, connects, pairs if the
radar isn't paired yet, and starts streaming. Without an address it scans for
6 s; if more than one LD2460 answers, it lists them and exits (status 2) so
you can pick one, or use `--ble best` to take the strongest:

```
ld2460: found 2 LD2460 radars; choose one with --ble ADDRESS:
  89:EC:12:F6:6A:62  LD2460-6A62  -63 dBm
  89:EC:12:F6:11:22  LD2460-1122  -80 dBm
```

With `auto` or `best`, reconnects always go back to the radar picked on the
first connection (by MAC), even if another one has a stronger signal by then.

From code: `stream_presence(ble="89:EC:12:F6:6A:62")` (or `ble="auto"` /
`ble="best"`).

Over BLE the module is a transparent UART bridge: service `FFF0` notifies the
same report frames on `FFF1`, and command frames are written to `FFF2`
(write-without-response). The radar only answers on a paired link, so on
Linux the tool registers a temporary BlueZ agent that accepts the Just Works
pairing (no PIN) when needed. BlueZ remembers the pairing, which just skips
that step next time; `bluetoothctl remove <MAC>` forgets it. The user running `ld2460` must be
allowed to register a BlueZ agent (the default `pi` user is).

A dropped BLE link, or a radar that isn't reachable yet, is retried
automatically: first after 2 s, doubling up to 60 s, and back to 2 s once
reports flow again. Each retry logs a warning on stderr. `--no-reconnect`
exits on the first disconnect instead. From code the same behaviour is
`stream_presence(ble=..., reconnect=True, retry_delay=2.0, max_retry_delay=60.0)`
(on by default for BLE, off for serial).

## Radar settings

`ld2460 config` reads and changes the settings stored on the radar. It works
over serial (default `--port`) and over BLE (`--ble`) alike, since both carry
the same command protocol; put the connection options before `config`:

```bash
ld2460 config show                              # serial, /dev/ttyACM0
ld2460 --ble config show --json                 # the only LD2460 in range

ld2460 --ble config set --range 4.5 --angles -45 45
ld2460 --port /dev/ttyUSB0 config set --mount wall --height 2.2 --tilt 25
ld2460 --ble config set --mount ceiling --range 3.5 --angles 0 360
ld2460 config reset --yes                       # factory settings
```

| Setting | Wall mount | Ceiling mount |
|---|---|---|
| `--range` (m) | 0–6 | 0–4 |
| `--angles START END` (°) | −60 to 60 | 0 to 360 |
| `--height` (m) | 1.6–2.6 | n/a |
| `--tilt` (°) | 0–30 | n/a |
| `--sensitivity` | high / medium / low | high / medium / low |

Anything not given keeps its stored value. Values are checked against these
limits before anything is written, then the settings are read back and
printed. The detection range is stored separately for each mounting mode.
Hi-Link's documents call the modes "side" and "top"; this tool says wall and
ceiling. The protocol document marks sensitivity as reserved, so it may have
no effect. Settings survive a power cycle. Commands are re-sent until the
radar answers, since it ignores some requests.

### Orientation: which way is +X, +Y and 0°

Directions come from the Hi-Link module manual (§7, Figures 8 and 9).

**Finding "up" on the module.** The antenna side is the side with the gold
square patches; the chips and pin headers are on the other side. The antenna
side has silkscreen at both short ends:

- the **IO end** reads `IO1 IO2 IO3 IO4` and `Rx Tx GND 3.3V` (the UART2
  header) and sits next to the antenna patches;
- the **5V end** reads `Tx Rx` and `GND 5V`.

Hold the board with the antenna side towards you and the IO end at the top.
That is the orientation of the manual's figures:

```
          IO end  (IO1–IO4, Rx Tx GND 3.3V)        ceiling: −Y
        ┌─────────────────────┐
        │   ▢     ▢     ▢     │  antenna patches
  −X ◄──┤                     ├──► +X   (your right, facing the antenna)
        │                     │
        │                     │
        └─────────────────────┘
          5V end  (Tx Rx, GND 5V)                  ceiling: +Y
```

**"Right" means your right as you face the antenna side.** Seen from the
radar, +X is on its left.

**Wall mount.** +Y points straight out of the antenna face into the room; X
runs across the board's 32 mm width. 0° is straight ahead, negative angles
are on the −X side (your left as you face the radar), positive on the +X side,
limited to ±60°. For angles to read left/right, mount the board upright with
the IO end at the top. With the 5V end at the top, left and right swap.
Mounted sideways (long edge horizontal), X and the angles measure up/down
instead of left/right.

**Ceiling mount.** Standing below and looking up, you see the antenna side, so
use the diagram as you see it from the floor. The radar covers a disc on the
floor around the point below it; `--range` is the radius (up to 4 m).
- +X is to your right, +Y towards the 5V end (the manual's "lower side").
- **0° points to +X.**
- In the manual's Figure 9, angles increase towards the IO end. That puts
  90° towards the IO end (−Y), 180° at −X and 270° towards the 5V end (+Y).
  It's counter-clockwise as seen from below.

`--angles START END` selects the slice from START to END. Examples:
- `0 360`: the whole disc (factory setting).
- `0 180`: the half towards the IO end.
- `90 270`: the half on the −X side.

START must be below END, so a slice crossing 0° (e.g. 300° to 30°) can't be
set. Turn the radar instead so the area you want doesn't straddle +X.

> **Unverified:** Hi-Link's own app draws the ceiling slice the other way
> round relative to the reported Y (90° at +Y, the 5V end), contradicting
> Figure 9. To check on your installation:
> 1. Set `config set --mount ceiling --angles 0 180`.
> 2. Stand below the radar on the IO side (−Y), then on the 5V side (+Y).
> 3. Note which side the radar still reports. If it's the IO side, Figure 9
>    is right.

From code: `RadarConfigurator(reader, writer)` with `read_config()`,
`apply(range_m=..., start_angle_deg=..., ...)` and `factory_reset()`, on any
transport from `ld2460.transport.open_transport`.

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

## Live dashboard (optional)

A small web dashboard can show every sensor's presence live — one card per
screen with person icons coloured by motion (approaching / moving away / static).
Needs the `server` extra (`aiohttp`):

```bash
pip install -e ".[server]"          # or "hlk-ld2460-presence[server]"

# 1. start the dashboard
ld2460-server --port 8099           # open http://localhost:8099

# 2. point a sensor at it (one per screen)
ld2460 --reporter http --server-url http://localhost:8099 --screen-name "office"
```

Screens auto-register on first report and grey out when a sensor goes silent.
`--reporter http` can be combined with `text`/`json`.

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
