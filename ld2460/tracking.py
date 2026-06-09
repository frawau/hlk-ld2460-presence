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

        for tid in [
            t for t, tr in self._tracks.items() if now - tr.last_seen > self.age_out
        ]:
            del self._tracks[tid]

        persons = [
            self._to_person(tr) for tr in self._tracks.values() if tr.last_seen == now
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

    def _update_track(
        self, tr: _Track, x: float, y: float, dt: float, now: float
    ) -> None:
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
