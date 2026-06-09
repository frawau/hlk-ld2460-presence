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
