# HLK-LD2460 Presence Decoder — Design

Date: 2026-06-09

## Purpose

Decode the serial output of a Hi-Link **HLK-LD2460** 24 GHz multi-target tracking
radar (connected via a USB-serial adapter, default `/dev/ttyACM0`) and report, in
real time:

- **Presence** — whether any person is detected.
- **Person count** — number of tracked targets.
- **Motion state per person** — `STATIC`, `APPROACHING` (moving towards the
  sensor), or `MOVING_AWAY`.

The tool is an asyncio Python application with a **pluggable reporter** layer so
output sinks (console now; HTTP API / MQTT later) can be added without touching
the core.

## Protocol facts (from HLK-LD2460 Serial Port Communication Protocol V1.0)

UART: **115200 bps, 8 data bits, 1 stop bit, no parity, no flow control**. Radar
auto-reports by default when powered on.

### Reporting frame (radar → host, function code `0x04`)

```
F4 F3 F2 F1 | 04 | LEN(2, LE) | <X(2,LE) Y(2,LE)> * N | F8 F7 F6 F5
 header(4)    func   length        data content (4 B/target)   tail(4)
```

- `LEN` is the **total packet length in bytes**, little-endian, equal to
  `N*4 + 11` where `N` is the number of targets.
- Number of people `N = (LEN - 11) / 4`.
- Each target: signed 16-bit little-endian **X** then **Y**, unit **0.1 m**
  (value / 10 = metres). X is the lateral axis, Y the forward/depth axis.
- Worked example from the datasheet — one target at (1.5, 2.3):
  `F4 F3 F2 F1 04 0F 00 0F 00 17 00 F8 F7 F6 F5`
  (`LEN = 0x000F = 15` → `N = 1`; `X = 0x000F = 15 → 1.5 m`;
  `Y = 0x0017 = 23 → 2.3 m`).

### Key consequence

**The protocol carries no speed or motion-state field — only X/Y positions.**
`STATIC / APPROACHING / MOVING_AWAY` must therefore be **derived** by tracking
each target across frames and measuring the change in its radial distance from
the sensor over time.

### Useful command frames (host → radar)

- Enable reporting: `FD FC FB FA 06 0C 00 01 04 03 02 01` (12 bytes; data byte `01`)
- Disable reporting: `FD FC FB FA 06 0C 00 00 04 03 02 01` (12 bytes; data byte `00`)
- Restart: `FD FC FB FA 0D 0C 00 01 04 03 02 01` (12 bytes; data byte `01`)

Command frame structure: `header(4) + func(1) + length(2, LE) + data + tail(4)`,
where `length` is the total byte count (12 for a single data byte).

Command frames use header `FD FC FB FA` and tail `04 03 02 01` (distinct from the
reporting frame markers).

## Architecture

Package `ld2460/`, run via `python -m ld2460`.

### Modules

- **`protocol.py`** — protocol constants and the frame codec.
  - `parse_report_frame(payload) -> list[tuple[float, float]]` returns targets in
    metres.
  - `FrameReader` is a streaming, resynchronising parser: it scans a raw byte
    buffer for the `F4 F3 F2 F1` header, reads the length, validates the
    `F8 F7 F6 F5` tail and `LEN == N*4 + 11`, and yields complete validated
    frames. Garbage/partial data triggers a header re-scan rather than a crash.
  - Command builders (`enable_reporting()`, `disable_reporting()`, `restart()`).

- **`transport.py`** — asyncio serial transport. `open_byte_stream(port, baud)`
  yields chunks of bytes. Primary implementation uses `serial_asyncio` streams.
  The transport is isolated behind this one function so it can be swapped for a
  thread-bridged `pyserial` reader if `serial_asyncio` has a Python 3.14
  compatibility issue.

- **`tracking.py`** — `Tracker`.
  - Input: per-frame list of `(x, y)` targets.
  - Greedy nearest-neighbour association of targets to existing tracks, gated by
    a maximum allowed jump between frames (new track if no match within gate).
  - Stable integer track IDs; tracks unseen for an age-out window are dropped.
  - Each track keeps an EMA-smoothed **radial distance** `r = hypot(x, y)` and
    its velocity `v = d(r)/dt`, with `dt` taken from frame arrival timestamps
    (so motion is independent of the radar's frame rate).
  - Classification dead-band: `|v| < static_threshold` → `STATIC`; `v < 0`
    (distance closing) → `APPROACHING`; `v > 0` → `MOVING_AWAY`. A track reports
    `UNKNOWN` until it has enough samples for a confident velocity.

- **`model.py`** — domain types.
  - `Motion` enum: `STATIC`, `APPROACHING`, `MOVING_AWAY`, `UNKNOWN`.
  - `Person(id, x, y, distance, angle, motion)` — `distance` is radial metres,
    `angle` is `degrees(atan2(x, y))` for information.
  - `PresenceReport(timestamp, count, persons)`.

- **`reporters/`** — pluggable output layer.
  - `Reporter` interface: async `start()`, `report(PresenceReport)`, `close()`.
  - `ConsoleTextReporter` — human-readable line/table per update.
  - `ConsoleJsonReporter` — one JSON object per update on stdout.
  - Future sinks (HTTP API, MQTT) implement the same interface; the core is
    unchanged. Reporters are async so network sinks never block the pipeline.

- **`__main__.py`** — CLI + orchestration.
  - argparse: `--port` (default `/dev/ttyACM0`), `--baud` (default `115200`),
    `--reporter {text,json}` (repeatable), `--static-threshold` (m/s),
    `--enable-on-start` (send the enable-reporting command before listening).
  - Wires the pipeline and handles graceful shutdown on SIGINT/SIGTERM.

### Data flow

```
serial bytes → FrameReader → [(x,y), ...] → Tracker → PresenceReport
            → await reporter.report() for each configured reporter
```

A single asyncio pipeline. Reporters are awaited so a slow/networked sink applies
backpressure rather than dropping the loop.

## Error handling & robustness

- The protocol has **no checksum**; frame validity rests on header + tail +
  `LEN == N*4 + 11`. Invalid bytes cause a header re-scan.
- Serial read errors are logged; the read loop may attempt a bounded reconnect
  (kept simple — log and exit cleanly if the device disappears, unless reconnect
  is explicitly added).
- Motion quality is bounded by the radar's positional jitter; `--static-threshold`
  tunes the jitter-vs-sensitivity trade-off.

## Testing

- **`protocol.py`**: unit tests with the datasheet example frame and synthetic
  frames (0 targets, multiple targets, signed/negative X, truncated frame,
  garbage-then-valid resync, wrong tail).
- **`tracking.py`**: feed scripted target sequences and assert the classified
  motion (approaching as r decreases, moving-away as r increases, static within
  the dead-band, ID stability, age-out).
- **reporters**: assert `ConsoleJsonReporter` emits valid parseable JSON with the
  expected fields.
- Transport and end-to-end against real hardware are manual (requires the
  device); a recorded byte fixture can drive an offline integration test.

## Deliverables

- The `ld2460/` package.
- `requirements.txt` (`pyserial`, `pyserial-asyncio`).
- A `venv` for the project.
- `README.md` with setup and run commands.

## Out of scope (for now)

- Home Assistant / MQTT / HTTP integration (the reporter plugin is the seam).
- Radar configuration UI (install height/angle, sensitivity, detection range) —
  command builders exist in `protocol.py` but no CLI surface beyond
  `--enable-on-start`.
