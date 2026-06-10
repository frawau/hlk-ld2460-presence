from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _ScreenState:
    name: str
    report: dict
    last_seen: float


class ScreenRegistry:
    """In-memory latest-state-per-screen, with online/stale derivation.

    Pure logic: no clock of its own — callers pass `now` (monotonic seconds).
    """

    def __init__(self, offline_after: float = 10.0, drop_after: float = 300.0) -> None:
        self.offline_after = offline_after
        self.drop_after = drop_after
        self._screens: dict[str, _ScreenState] = {}

    def update(self, screen: str, report: dict, now: float) -> dict:
        self._screens[screen] = _ScreenState(screen, report, now)
        return self._as_dict(self._screens[screen], now)

    def _as_dict(self, st: _ScreenState, now: float) -> dict:
        age = now - st.last_seen
        return {
            "name": st.name,
            "report": st.report,
            "online": age <= self.offline_after,
            "last_seen_age": round(age, 1),
        }

    def snapshot(self, now: float) -> list[dict]:
        return [
            self._as_dict(st, now)
            for st in sorted(self._screens.values(), key=lambda s: s.name)
        ]

    def evict_stale(self, now: float) -> list[str]:
        dropped = [
            name
            for name, st in self._screens.items()
            if now - st.last_seen > self.drop_after
        ]
        for name in dropped:
            del self._screens[name]
        return dropped
