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


__all__ = ["Reporter"]
