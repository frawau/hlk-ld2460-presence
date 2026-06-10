import pytest

pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer

from ld2460.server.app import create_app


async def _client():
    client = TestClient(TestServer(create_app()))
    await client.start_server()
    return client


async def test_post_report_updates_state():
    client = await _client()
    try:
        resp = await client.post(
            "/api/report",
            json={"screen": "office", "report": {"count": 2, "persons": []}},
        )
        assert resp.status == 204
        ws = await client.ws_connect("/ws")
        msg = await ws.receive_json()
        assert msg["type"] == "state"
        assert "office" in [s["name"] for s in msg["screens"]]
        await ws.close()
    finally:
        await client.close()


async def test_ws_receives_broadcast_after_post():
    client = await _client()
    try:
        ws = await client.ws_connect("/ws")
        first = await ws.receive_json()
        assert first["type"] == "state"
        await client.post(
            "/api/report", json={"screen": "lab", "report": {"count": 1, "persons": []}}
        )
        msg = await ws.receive_json()
        assert msg["type"] == "screen"
        assert msg["screen"]["name"] == "lab"
        assert msg["screen"]["report"]["count"] == 1
        await ws.close()
    finally:
        await client.close()


async def test_bad_report_rejected():
    client = await _client()
    try:
        resp = await client.post("/api/report", json={"nope": 1})
        assert resp.status == 400
    finally:
        await client.close()
