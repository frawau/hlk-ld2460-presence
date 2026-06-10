import pytest

pytest.importorskip("aiohttp")
from aiohttp import web
from aiohttp.test_utils import TestServer

from ld2460.model import Motion, Person, PresenceReport
from ld2460.reporters.http_reporter import HttpReporter


def _report():
    p = Person(id=1, x=0.0, y=2.0, distance=2.0, angle=0.0, motion=Motion.APPROACHING)
    return PresenceReport(timestamp=1.0, count=1, persons=[p])


async def test_http_reporter_posts_payload():
    received = []

    async def handler(request):
        received.append(await request.json())
        return web.Response(status=204)

    app = web.Application()
    app.router.add_post("/api/report", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        reporter = HttpReporter(f"http://{server.host}:{server.port}", "office")
        await reporter.start()
        await reporter.report(_report())
        await reporter.close()
    finally:
        await server.close()

    assert len(received) == 1
    assert received[0]["screen"] == "office"
    assert received[0]["report"]["count"] == 1
    assert received[0]["report"]["persons"][0]["motion"] == "approaching"


async def test_http_reporter_swallows_connection_errors():
    # Nothing is listening on this port; report() must not raise.
    reporter = HttpReporter("http://127.0.0.1:1", "x", timeout=0.5)
    await reporter.start()
    await reporter.report(_report())  # best-effort, no exception
    await reporter.close()
