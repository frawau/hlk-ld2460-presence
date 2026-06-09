"""HLK-LD2460 presence decoder."""

from .app import iter_reports, run_pipeline, stream_presence
from .model import Motion, Person, PresenceReport
from .protocol import (
    FrameReader,
    build_report_frame,
    disable_reporting,
    enable_reporting,
    parse_report_frame,
    restart,
)
from .reporters import Reporter
from .tracking import Tracker

__version__ = "0.1.0"

__all__ = [
    "Motion",
    "Person",
    "PresenceReport",
    "Reporter",
    "Tracker",
    "FrameReader",
    "parse_report_frame",
    "build_report_frame",
    "enable_reporting",
    "disable_reporting",
    "restart",
    "run_pipeline",
    "iter_reports",
    "stream_presence",
    "__version__",
]
