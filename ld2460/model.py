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
