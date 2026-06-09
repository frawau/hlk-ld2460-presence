# HLK-LD2460 Presence Decoder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an asyncio Python tool that decodes the HLK-LD2460 radar serial stream and reports presence, person count, and per-person motion (static / approaching / moving away) to pluggable output sinks.

**Architecture:** A linear asyncio pipeline — serial bytes → streaming frame parser → multi-target tracker (derives motion from radial-distance change across frames) → `PresenceReport` → one or more async reporter plugins. Pure functions and injectable dependencies (clock, byte reader, output stream) keep every layer unit-testable without hardware.

**Tech Stack:** Python 3.14, asyncio, `pyserial` + `pyserial-asyncio` (verified to import on 3.14.4), `pytest` + `pytest-asyncio`. `black` for formatting.

**Conventions:** metric units, 24-hour timestamps. Run `black` on every modified `.py` file before committing. The project `venv` lives at `./venv`; run Python as `./venv/bin/python` and tests as `./venv/bin/pytest`.

---

## File Structure

```
ld2460/
  __init__.py
  model.py             # Motion enum, Person, PresenceReport
  protocol.py          # frame constants, parse_report_frame, build_report_frame, FrameReader, command builders
  tracking.py          # Tracker: association + radial-distance motion classification
  transport.py         # open_byte_stream() over serial_asyncio
  app.py               # run_pipeline() — testable orchestration
  __main__.py          # argparse CLI + asyncio.run + signal handling
  reporters/
    __init__.py        # Reporter abstract base
    console.py         # ConsoleTextReporter, ConsoleJsonReporter
tests/
  test_model.py
  test_protocol.py
  test_tracking.py
  test_reporters.py
  test_app.py
  test_cli.py
requirements.txt
pytest.ini
README.md
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `ld2460/__init__.py`
- Create: `ld2460/reporters/__init__.py` (empty for now; replaced in Task 7)
- Create: `tests/__init__.py`

- [ ] **Step 1: Write `requirements.txt`**

```
pyserial>=3.5
pyserial-asyncio>=0.6
pytest>=8
pytest-asyncio>=0.23
```

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Create empty package files**

`ld2460/__init__.py`:
```python
"""HLK-LD2460 presence decoder."""

__version__ = "0.1.0"
```

`ld2460/reporters/__init__.py`: (leave empty — defined in Task 7)

`tests/__init__.py`: (empty)

- [ ] **Step 4: Verify pytest collects nothing yet without error**

Run: `./venv/bin/pytest -q`
Expected: `no tests ran` (exit code 5) — confirms config loads.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pytest.ini ld2460/ tests/
git commit -m "chore: scaffold ld2460 package and test config"
```

---

### Task 2: Domain model

**Files:**
- Create: `ld2460/model.py`
- Test: `tests/test_model.py`

- [ ] **Step 1: Write the failing test**

`tests/test_model.py`:
```python
from ld2460.model import Motion, Person, PresenceReport


def test_person_to_dict():
    p = Person(id=1, x=-1.5, y=2.3, distance=2.74, angle=-33.1, motion=Motion.APPROACHING)
    assert p.to_dict() == {
        "id": 1,
        "x": -1.5,
        "y": 2.3,
        "distance": 2.74,
        "angle": -33.1,
        "motion": "approaching",
    }


def test_presence_report_present_and_dict():
    p = Person(id=1, x=0.0, y=2.0, distance=2.0, angle=0.0, motion=Motion.STATIC)
    report = PresenceReport(timestamp=12.5, count=1, persons=[p])
    assert report.present is True
    d = report.to_dict()
    assert d["present"] is True
    assert d["count"] == 1
    assert d["persons"][0]["motion"] == "static"


def test_empty_report_not_present():
    report = PresenceReport(timestamp=0.0, count=0, persons=[])
    assert report.present is False
    assert report.to_dict()["persons"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.model'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/model.py`:
```python
from __future__ import annotations

import enum
from dataclasses import dataclass


class Motion(enum.Enum):
    STATIC = "static"
    APPROACHING = "approaching"
    MOVING_AWAY = "moving_away"
    UNKNOWN = "unknown"


@dataclass
class Person:
    id: int
    x: float
    y: float
    distance: float
    angle: float
    motion: Motion

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "distance": round(self.distance, 3),
            "angle": round(self.angle, 1),
            "motion": self.motion.value,
        }


@dataclass
class PresenceReport:
    timestamp: float
    count: int
    persons: list[Person]

    @property
    def present(self) -> bool:
        return self.count > 0

    def to_dict(self) -> dict:
        return {
            "timestamp": round(self.timestamp, 3),
            "present": self.present,
            "count": self.count,
            "persons": [p.to_dict() for p in self.persons],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_model.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/model.py tests/test_model.py
git add ld2460/model.py tests/test_model.py
git commit -m "feat: add Motion/Person/PresenceReport domain model"
```

---

### Task 3: Report frame codec (`parse_report_frame` + `build_report_frame`)

**Files:**
- Create: `ld2460/protocol.py`
- Test: `tests/test_protocol.py`

- [ ] **Step 1: Write the failing test**

`tests/test_protocol.py`:
```python
import struct

import pytest

from ld2460.protocol import (
    REPORT_HEADER,
    REPORT_TAIL,
    FrameError,
    build_report_frame,
    parse_report_frame,
)


def test_datasheet_example_single_target():
    # From HLK-LD2460 protocol V1.0: target at (1.5, 2.3)
    frame = bytes.fromhex("F4F3F2F1 04 0F00 0F00 1700 F8F7F6F5".replace(" ", ""))
    targets = parse_report_frame(frame)
    assert targets == [(1.5, 2.3)]


def test_zero_targets():
    frame = bytes.fromhex("F4F3F2F1 04 0B00 F8F7F6F5".replace(" ", ""))
    assert parse_report_frame(frame) == []


def test_multiple_and_negative_x():
    frame = build_report_frame([(-1.5, 2.0), (0.7, 4.2)])
    assert parse_report_frame(frame) == [(-1.5, 2.0), (0.7, 4.2)]


def test_build_matches_datasheet():
    assert build_report_frame([(1.5, 2.3)]).hex() == "f4f3f2f1040f000f001700f8f7f6f5"


def test_bad_header_raises():
    frame = bytes.fromhex("AABBCCDD 04 0B00 F8F7F6F5".replace(" ", ""))
    with pytest.raises(FrameError):
        parse_report_frame(frame)


def test_bad_tail_raises():
    frame = bytes.fromhex("F4F3F2F1 04 0B00 11223344".replace(" ", ""))
    with pytest.raises(FrameError):
        parse_report_frame(frame)


def test_length_mismatch_raises():
    frame = bytes.fromhex("F4F3F2F1 04 FF00 0F00 1700 F8F7F6F5".replace(" ", ""))
    with pytest.raises(FrameError):
        parse_report_frame(frame)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.protocol'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/protocol.py`:
```python
from __future__ import annotations

import struct

REPORT_HEADER = bytes([0xF4, 0xF3, 0xF2, 0xF1])
REPORT_TAIL = bytes([0xF8, 0xF7, 0xF6, 0xF5])
REPORT_FUNC = 0x04

CMD_HEADER = bytes([0xFD, 0xFC, 0xFB, 0xFA])
CMD_TAIL = bytes([0x04, 0x03, 0x02, 0x01])

# Minimum report frame: header(4) + func(1) + length(2) + tail(4)
_REPORT_OVERHEAD = 11


class FrameError(ValueError):
    """Raised when a byte sequence is not a valid LD2460 report frame."""


def parse_report_frame(frame: bytes) -> list[tuple[float, float]]:
    """Decode a complete report frame into a list of (x, y) targets in metres."""
    if len(frame) < _REPORT_OVERHEAD:
        raise FrameError("frame too short")
    if frame[0:4] != REPORT_HEADER:
        raise FrameError("bad header")
    if frame[4] != REPORT_FUNC:
        raise FrameError("bad function code")
    length = int.from_bytes(frame[5:7], "little")
    if length != len(frame):
        raise FrameError(f"length mismatch: field={length} actual={len(frame)}")
    if (length - _REPORT_OVERHEAD) % 4 != 0:
        raise FrameError("invalid payload length")
    if frame[-4:] != REPORT_TAIL:
        raise FrameError("bad tail")
    n = (length - _REPORT_OVERHEAD) // 4
    targets: list[tuple[float, float]] = []
    offset = 7
    for _ in range(n):
        x_raw, y_raw = struct.unpack_from("<hh", frame, offset)
        targets.append((x_raw / 10.0, y_raw / 10.0))
        offset += 4
    return targets


def build_report_frame(targets: list[tuple[float, float]]) -> bytes:
    """Build a report frame from (x, y) metre coordinates (inverse of parse)."""
    body = b"".join(
        struct.pack("<hh", round(x * 10), round(y * 10)) for x, y in targets
    )
    length = _REPORT_OVERHEAD + len(body)
    return (
        REPORT_HEADER
        + bytes([REPORT_FUNC])
        + length.to_bytes(2, "little")
        + body
        + REPORT_TAIL
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_protocol.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/protocol.py tests/test_protocol.py
git add ld2460/protocol.py tests/test_protocol.py
git commit -m "feat: add LD2460 report frame parse/build codec"
```

---

### Task 4: Streaming `FrameReader` with resync

**Files:**
- Modify: `ld2460/protocol.py` (append `FrameReader`)
- Test: `tests/test_protocol.py` (append)

- [ ] **Step 1: Write the failing test (append to `tests/test_protocol.py`)**

```python
from ld2460.protocol import FrameReader


def test_framereader_single_frame():
    fr = FrameReader()
    frame = build_report_frame([(1.5, 2.3)])
    assert fr.feed(frame) == [[(1.5, 2.3)]]


def test_framereader_split_across_chunks():
    fr = FrameReader()
    frame = build_report_frame([(0.0, 2.0)])
    assert fr.feed(frame[:5]) == []
    assert fr.feed(frame[5:]) == [[(0.0, 2.0)]]


def test_framereader_resyncs_past_garbage():
    fr = FrameReader()
    frame = build_report_frame([(0.0, 2.0)])
    out = fr.feed(b"\x00\x11garbage" + frame)
    assert out == [[(0.0, 2.0)]]


def test_framereader_two_frames_in_one_feed():
    fr = FrameReader()
    a = build_report_frame([(1.0, 1.0)])
    b = build_report_frame([(2.0, 2.0), (3.0, 3.0)])
    assert fr.feed(a + b) == [[(1.0, 1.0)], [(2.0, 2.0), (3.0, 3.0)]]


def test_framereader_drops_frame_with_bad_tail():
    fr = FrameReader()
    good = build_report_frame([(0.0, 2.0)])
    bad = bytearray(build_report_frame([(0.0, 5.0)]))
    bad[-1] = 0x00  # corrupt tail
    out = fr.feed(bytes(bad) + good)
    assert out == [[(0.0, 2.0)]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_protocol.py -k framereader -v`
Expected: FAIL — `ImportError: cannot import name 'FrameReader'`

- [ ] **Step 3: Write minimal implementation (append to `ld2460/protocol.py`)**

```python
_MAX_FRAME = 4096  # sanity bound for the length field


class FrameReader:
    """Stateful, resynchronising parser. Feed raw bytes, get decoded frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[list[tuple[float, float]]]:
        self._buf.extend(data)
        frames: list[list[tuple[float, float]]] = []
        while True:
            frame = self._extract_one()
            if frame is None:
                break
            try:
                frames.append(parse_report_frame(frame))
            except FrameError:
                pass  # already resynced past the header in _extract_one
        return frames

    def _extract_one(self) -> bytes | None:
        idx = self._buf.find(REPORT_HEADER)
        if idx == -1:
            # keep a possible partial header at the tail of the buffer
            if len(self._buf) > 3:
                del self._buf[:-3]
            return None
        if idx > 0:
            del self._buf[:idx]
        if len(self._buf) < 7:
            return None  # need header + func + length
        length = int.from_bytes(self._buf[5:7], "little")
        if (
            length < _REPORT_OVERHEAD
            or length > _MAX_FRAME
            or (length - _REPORT_OVERHEAD) % 4 != 0
        ):
            del self._buf[:4]  # corrupt length — skip this header, resync
            return None
        if len(self._buf) < length:
            return None  # wait for the rest of the frame
        frame = bytes(self._buf[:length])
        if frame[-4:] != REPORT_TAIL:
            del self._buf[:4]  # bad tail — skip header, resync
            return None
        del self._buf[:length]
        return frame
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_protocol.py -v`
Expected: PASS (12 tests total)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/protocol.py tests/test_protocol.py
git add ld2460/protocol.py tests/test_protocol.py
git commit -m "feat: add streaming FrameReader with resync"
```

---

### Task 5: Command builders

**Files:**
- Modify: `ld2460/protocol.py` (append)
- Test: `tests/test_protocol.py` (append)

- [ ] **Step 1: Write the failing test (append to `tests/test_protocol.py`)**

```python
from ld2460.protocol import disable_reporting, enable_reporting, restart


def test_enable_reporting_bytes():
    assert enable_reporting().hex() == "fdfcfbfa060c0001" "04030201"


def test_disable_reporting_bytes():
    assert disable_reporting().hex() == "fdfcfbfa060c0000" "04030201"


def test_restart_bytes():
    assert restart().hex() == "fdfcfbfa0d0c0001" "04030201"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_protocol.py -k reporting_bytes -v`
Expected: FAIL — `ImportError: cannot import name 'enable_reporting'`

- [ ] **Step 3: Write minimal implementation (append to `ld2460/protocol.py`)**

```python
def _command(func: int, data: bytes = b"") -> bytes:
    length = len(CMD_HEADER) + 1 + 2 + len(data) + len(CMD_TAIL)
    return (
        CMD_HEADER + bytes([func]) + length.to_bytes(2, "little") + data + CMD_TAIL
    )


def enable_reporting() -> bytes:
    return _command(0x06, b"\x01")


def disable_reporting() -> bytes:
    return _command(0x06, b"\x00")


def restart() -> bytes:
    return _command(0x0D, b"\x01")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_protocol.py -k reporting_bytes -v`
Expected: PASS (3 tests). Also run full file: `./venv/bin/pytest tests/test_protocol.py -q` → 15 passed.

- [ ] **Step 5: Format and commit**

```bash
black ld2460/protocol.py tests/test_protocol.py
git add ld2460/protocol.py tests/test_protocol.py
git commit -m "feat: add enable/disable/restart command builders"
```

---

### Task 6: Multi-target tracker with motion classification

**Files:**
- Create: `ld2460/tracking.py`
- Test: `tests/test_tracking.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tracking.py`:
```python
from ld2460.model import Motion
from ld2460.tracking import Tracker


def _feed(tracker, sequence):
    """sequence: list of (now, [(x, y), ...]); returns the last PresenceReport."""
    report = None
    for now, targets in sequence:
        report = tracker.update(targets, now)
    return report


def test_no_targets_no_presence():
    t = Tracker()
    report = t.update([], now=0.0)
    assert report.present is False
    assert report.count == 0


def test_count_matches_targets():
    t = Tracker()
    report = t.update([(0.0, 2.0), (1.0, 3.0)], now=0.0)
    assert report.count == 2
    assert report.present is True


def test_static_target():
    t = Tracker(min_samples=3)
    seq = [(i * 0.1, [(0.0, 2.0)]) for i in range(5)]
    report = _feed(t, seq)
    assert report.persons[0].motion is Motion.STATIC


def test_approaching_target():
    t = Tracker(min_samples=3)
    seq = [(i * 0.1, [(0.0, 3.0 - i * 0.4)]) for i in range(5)]
    report = _feed(t, seq)
    assert report.persons[0].motion is Motion.APPROACHING


def test_moving_away_target():
    t = Tracker(min_samples=3)
    seq = [(i * 0.1, [(0.0, 1.0 + i * 0.4)]) for i in range(5)]
    report = _feed(t, seq)
    assert report.persons[0].motion is Motion.MOVING_AWAY


def test_track_id_is_stable():
    t = Tracker()
    r0 = t.update([(0.0, 2.0)], now=0.0)
    r1 = t.update([(0.05, 2.05)], now=0.1)
    assert r0.persons[0].id == r1.persons[0].id


def test_track_ages_out():
    t = Tracker(age_out=0.3)
    t.update([(0.0, 2.0)], now=0.0)
    report = t.update([], now=1.0)
    assert report.count == 0


def test_unknown_until_min_samples():
    t = Tracker(min_samples=3)
    report = t.update([(0.0, 2.0)], now=0.0)
    assert report.persons[0].motion is Motion.UNKNOWN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_tracking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.tracking'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/tracking.py`:
```python
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Motion, Person, PresenceReport


@dataclass
class _Track:
    id: int
    x: float
    y: float
    distance: float  # EMA-smoothed radial distance (m)
    velocity: float  # EMA-smoothed radial velocity (m/s); <0 = closing
    samples: int
    last_seen: float


class Tracker:
    """Associates per-frame targets into stable tracks and classifies motion.

    Motion is derived from the change in each track's radial distance
    (sqrt(x^2 + y^2)) over time, since the LD2460 protocol reports only
    position, not velocity.
    """

    def __init__(
        self,
        static_threshold: float = 0.05,
        gate: float = 1.0,
        age_out: float = 0.5,
        smoothing: float = 0.5,
        min_samples: int = 3,
    ) -> None:
        self.static_threshold = static_threshold
        self.gate = gate
        self.age_out = age_out
        self.smoothing = smoothing
        self.min_samples = min_samples
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    def update(self, targets: list[tuple[float, float]], now: float) -> PresenceReport:
        matched = self._associate(targets)

        for tid, i in matched.items():
            tr = self._tracks[tid]
            x, y = targets[i]
            dt = now - tr.last_seen
            self._update_track(tr, x, y, dt, now)

        for i, (x, y) in enumerate(targets):
            if i in matched.values():
                continue
            self._tracks[self._next_id] = _Track(
                id=self._next_id,
                x=x,
                y=y,
                distance=math.hypot(x, y),
                velocity=0.0,
                samples=1,
                last_seen=now,
            )
            self._next_id += 1

        for tid in [t for t, tr in self._tracks.items() if now - tr.last_seen > self.age_out]:
            del self._tracks[tid]

        persons = [
            self._to_person(tr)
            for tr in self._tracks.values()
            if tr.last_seen == now
        ]
        persons.sort(key=lambda p: p.id)
        return PresenceReport(timestamp=now, count=len(persons), persons=persons)

    def _associate(self, targets: list[tuple[float, float]]) -> dict[int, int]:
        pairs = []
        for tid, tr in self._tracks.items():
            for i, (x, y) in enumerate(targets):
                d = math.hypot(x - tr.x, y - tr.y)
                if d <= self.gate:
                    pairs.append((d, tid, i))
        pairs.sort(key=lambda p: p[0])
        matched: dict[int, int] = {}
        used_targets: set[int] = set()
        for _, tid, i in pairs:
            if tid in matched or i in used_targets:
                continue
            matched[tid] = i
            used_targets.add(i)
        return matched

    def _update_track(self, tr: _Track, x: float, y: float, dt: float, now: float) -> None:
        a = self.smoothing
        prev = tr.distance
        r = math.hypot(x, y)
        tr.x = x
        tr.y = y
        tr.distance = a * r + (1 - a) * tr.distance
        if dt > 0:
            inst_v = (tr.distance - prev) / dt
            tr.velocity = a * inst_v + (1 - a) * tr.velocity
        tr.samples += 1
        tr.last_seen = now

    def _classify(self, tr: _Track) -> Motion:
        if tr.samples < self.min_samples:
            return Motion.UNKNOWN
        if abs(tr.velocity) < self.static_threshold:
            return Motion.STATIC
        return Motion.APPROACHING if tr.velocity < 0 else Motion.MOVING_AWAY

    def _to_person(self, tr: _Track) -> Person:
        angle = math.degrees(math.atan2(tr.x, tr.y)) if (tr.x or tr.y) else 0.0
        return Person(
            id=tr.id,
            x=tr.x,
            y=tr.y,
            distance=tr.distance,
            angle=angle,
            motion=self._classify(tr),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_tracking.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/tracking.py tests/test_tracking.py
git add ld2460/tracking.py tests/test_tracking.py
git commit -m "feat: add multi-target tracker with radial motion classification"
```

---

### Task 7: Reporter plugin interface + console reporters

**Files:**
- Modify: `ld2460/reporters/__init__.py`
- Create: `ld2460/reporters/console.py`
- Test: `tests/test_reporters.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reporters.py`:
```python
import io
import json

from ld2460.model import Motion, Person, PresenceReport
from ld2460.reporters.console import ConsoleJsonReporter, ConsoleTextReporter


def _report():
    p = Person(id=1, x=0.0, y=2.0, distance=2.0, angle=0.0, motion=Motion.APPROACHING)
    return PresenceReport(timestamp=1.0, count=1, persons=[p])


async def test_json_reporter_emits_parseable_json():
    buf = io.StringIO()
    r = ConsoleJsonReporter(stream=buf)
    await r.start()
    await r.report(_report())
    await r.close()
    obj = json.loads(buf.getvalue().strip())
    assert obj["count"] == 1
    assert obj["present"] is True
    assert obj["persons"][0]["motion"] == "approaching"


async def test_text_reporter_present_line():
    buf = io.StringIO()
    r = ConsoleTextReporter(stream=buf)
    await r.report(_report())
    out = buf.getvalue()
    assert "present=1" in out
    assert "approaching" in out


async def test_text_reporter_absence_line():
    buf = io.StringIO()
    r = ConsoleTextReporter(stream=buf)
    await r.report(PresenceReport(timestamp=0.0, count=0, persons=[]))
    assert "no presence" in buf.getvalue()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_reporters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.reporters.console'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/reporters/__init__.py`:
```python
from __future__ import annotations

import abc

from ..model import PresenceReport


class Reporter(abc.ABC):
    """Output sink plugin. Subclass and implement report() to add a new sink."""

    async def start(self) -> None:  # noqa: B027 - optional hook
        """Optional async setup (open sockets, connect, etc.)."""

    @abc.abstractmethod
    async def report(self, report: PresenceReport) -> None:
        """Emit one presence update."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Optional async teardown."""
```

`ld2460/reporters/console.py`:
```python
from __future__ import annotations

import json
import sys
from typing import TextIO

from ..model import PresenceReport
from . import Reporter


class ConsoleJsonReporter(Reporter):
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    async def report(self, report: PresenceReport) -> None:
        self._stream.write(json.dumps(report.to_dict()) + "\n")
        self._stream.flush()


class ConsoleTextReporter(Reporter):
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    async def report(self, report: PresenceReport) -> None:
        if not report.present:
            line = "no presence"
        else:
            parts = [
                f"#{p.id} d={p.distance:.1f}m a={p.angle:+.0f}° {p.motion.value}"
                for p in report.persons
            ]
            line = f"present={report.count} | " + " | ".join(parts)
        self._stream.write(line + "\n")
        self._stream.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_reporters.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/reporters/ tests/test_reporters.py
git add ld2460/reporters/ tests/test_reporters.py
git commit -m "feat: add Reporter plugin base and console text/json reporters"
```

---

### Task 8: Orchestration pipeline (`run_pipeline`)

**Files:**
- Create: `ld2460/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

`tests/test_app.py`:
```python
import itertools

from ld2460.app import run_pipeline
from ld2460.model import Motion
from ld2460.protocol import build_report_frame
from ld2460.reporters import Reporter
from ld2460.tracking import Tracker


class FakeReader:
    """Yields each queued chunk once, then b'' to signal EOF."""

    def __init__(self, chunks):
        self._chunks = list(chunks) + [b""]
        self._i = 0

    async def read(self, _n):
        chunk = self._chunks[self._i]
        self._i += 1
        return chunk


class RecordingReporter(Reporter):
    def __init__(self):
        self.reports = []
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def report(self, report):
        self.reports.append(report)

    async def close(self):
        self.closed = True


async def test_pipeline_decodes_and_reports():
    # Person approaching: distance shrinks frame to frame.
    frames = [build_report_frame([(0.0, 3.0 - i * 0.4)]) for i in range(5)]
    reader = FakeReader(frames)
    rec = RecordingReporter()
    clock = itertools.count(0, 1)  # 0,1,2,... deterministic seconds
    await run_pipeline(
        reader, Tracker(min_samples=3), [rec], clock=lambda: next(clock)
    )
    assert rec.started and rec.closed
    assert len(rec.reports) == 5
    assert rec.reports[-1].count == 1
    assert rec.reports[-1].persons[0].motion is Motion.APPROACHING


async def test_pipeline_stops_on_eof():
    reader = FakeReader([])  # immediately EOF
    rec = RecordingReporter()
    await run_pipeline(reader, Tracker(), [rec], clock=lambda: 0.0)
    assert rec.reports == []
    assert rec.closed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.app'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/app.py`:
```python
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

from .protocol import FrameReader
from .reporters import Reporter
from .tracking import Tracker


class ByteReader(Protocol):
    async def read(self, n: int) -> bytes: ...


async def run_pipeline(
    reader: ByteReader,
    tracker: Tracker,
    reporters: Sequence[Reporter],
    *,
    clock: Callable[[], float] = time.monotonic,
    read_size: int = 256,
    stop=None,
) -> None:
    """Drive the decode pipeline until EOF or `stop` is set.

    reader: object with `async read(n) -> bytes` (serial stream or fake).
    stop:   optional asyncio.Event for graceful shutdown.
    """
    frame_reader = FrameReader()
    for r in reporters:
        await r.start()
    try:
        while stop is None or not stop.is_set():
            data = await reader.read(read_size)
            if not data:
                break
            for targets in frame_reader.feed(data):
                report = tracker.update(targets, clock())
                for r in reporters:
                    await r.report(report)
    finally:
        for r in reporters:
            await r.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_app.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/app.py tests/test_app.py
git add ld2460/app.py tests/test_app.py
git commit -m "feat: add run_pipeline orchestration"
```

---

### Task 9: Serial transport

**Files:**
- Create: `ld2460/transport.py`

- [ ] **Step 1: Write implementation (no unit test — requires hardware; verified by import + manual smoke)**

`ld2460/transport.py`:
```python
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
```

- [ ] **Step 2: Verify it imports**

Run: `./venv/bin/python -c "from ld2460.transport import open_byte_stream; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Format and commit**

```bash
black ld2460/transport.py
git add ld2460/transport.py
git commit -m "feat: add serial_asyncio byte-stream transport"
```

---

### Task 10: CLI entry point

**Files:**
- Create: `ld2460/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from ld2460.__main__ import build_reporters, parse_args
from ld2460.reporters.console import ConsoleJsonReporter, ConsoleTextReporter


def test_defaults():
    args = parse_args([])
    assert args.port == "/dev/ttyACM0"
    assert args.baud == 115200
    assert args.reporter == ["text"]
    assert args.enable_on_start is False


def test_reporter_selection():
    args = parse_args(["--reporter", "json", "--reporter", "text"])
    assert args.reporter == ["json", "text"]


def test_build_reporters_maps_names():
    reporters = build_reporters(["text", "json"])
    assert isinstance(reporters[0], ConsoleTextReporter)
    assert isinstance(reporters[1], ConsoleJsonReporter)


def test_custom_port_and_threshold():
    args = parse_args(["--port", "/dev/ttyUSB0", "--static-threshold", "0.1"])
    assert args.port == "/dev/ttyUSB0"
    assert args.static_threshold == 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.__main__'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/__main__.py`:
```python
from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Sequence

from .app import run_pipeline
from .protocol import enable_reporting
from .reporters import Reporter
from .reporters.console import ConsoleJsonReporter, ConsoleTextReporter
from .tracking import Tracker
from .transport import open_byte_stream

_REPORTER_FACTORIES = {
    "text": ConsoleTextReporter,
    "json": ConsoleJsonReporter,
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ld2460", description="HLK-LD2460 presence decoder"
    )
    p.add_argument("--port", default="/dev/ttyACM0", help="serial device")
    p.add_argument("--baud", type=int, default=115200, help="baud rate")
    p.add_argument(
        "--reporter",
        action="append",
        choices=sorted(_REPORTER_FACTORIES),
        help="output sink (repeatable); default: text",
    )
    p.add_argument(
        "--static-threshold",
        type=float,
        default=0.05,
        help="radial speed (m/s) below which motion is STATIC",
    )
    p.add_argument(
        "--enable-on-start",
        action="store_true",
        help="send the enable-reporting command before listening",
    )
    args = p.parse_args(argv)
    if not args.reporter:
        args.reporter = ["text"]
    return args


def build_reporters(names: Sequence[str]) -> list[Reporter]:
    return [_REPORTER_FACTORIES[n]() for n in names]


async def _amain(args: argparse.Namespace) -> None:
    reader, writer = await open_byte_stream(args.port, args.baud)
    if args.enable_on_start:
        writer.write(enable_reporting())
        await writer.drain()
    tracker = Tracker(static_threshold=args.static_threshold)
    reporters = build_reporters(args.reporter)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX
            pass

    await run_pipeline(reader, tracker, reporters, stop=stop)


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(_amain(parse_args(argv)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_cli.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Format and commit**

```bash
black ld2460/__main__.py tests/test_cli.py
git add ld2460/__main__.py tests/test_cli.py
git commit -m "feat: add CLI entry point"
```

---

### Task 11: README and full verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
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
````

- [ ] **Step 2: Run the full test suite**

Run: `./venv/bin/pytest -q`
Expected: PASS — all tests green (model 3, protocol 15, tracking 8, reporters 3, app 2, cli 4 = 35).

- [ ] **Step 3: Format-check the whole package**

Run: `black --check ld2460 tests`
Expected: `All done!` (no files would be reformatted).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Self-Review Notes

- **Spec coverage:** UART params & frame format → Tasks 3–5; presence/count → Task 6 (`PresenceReport`); derived motion via radial distance → Task 6; pluggable reporters (text/json now) → Task 7; asyncio pipeline → Task 8; serial transport → Task 9; CLI (`--port`, `--reporter`, `--static-threshold`, `--enable-on-start`) → Task 10; venv/requirements/README → Tasks 1 & 11; tests per module → every task.
- **Type consistency:** `parse_report_frame`/`build_report_frame` return/accept `list[tuple[float, float]]`; `Tracker.update(targets, now)` → `PresenceReport`; `Reporter.report(PresenceReport)`; `run_pipeline(reader, tracker, reporters, *, clock, read_size, stop)` — names match across Tasks 6, 8, 10.
- **Hardware-dependent gaps:** `transport.py` and the real end-to-end serial read are validated manually against the device; `run_pipeline` is covered offline with a `FakeReader` driven by `build_report_frame` fixtures.
- **Signed X confirmed:** the module manual specifies side-mount coordinate
  range X ∈ [−6, 6] m and angle ∈ [−60°, 60°] (top-mount X/Y ∈ [−4, 4] m), so
  X (and top-mount Y) are signed little-endian int16 at 0.1 m units, as decoded.
  See `docs/hardware-enclosure-notes.md`.
