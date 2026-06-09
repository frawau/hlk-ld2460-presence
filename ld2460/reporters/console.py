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
                f"#{p.id} d={p.distance:.1f}m a={p.angle:+.0f}deg {p.motion.value}"
                for p in report.persons
            ]
            line = f"present={report.count} | " + " | ".join(parts)
        self._stream.write(line + "\n")
        self._stream.flush()
