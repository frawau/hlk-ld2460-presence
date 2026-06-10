import pytest

pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer

from ld2460.server.app import create_app


async def test_index_and_assets_served():
    client = TestClient(TestServer(create_app()))
    await client.start_server()
    try:
        idx = await client.get("/")
        assert idx.status == 200
        html = await idx.text()
        assert "LD2460" in html
        assert "app.js" in html
        js = await client.get("/static/app.js")
        assert js.status == 200
        assert "WebSocket" in await js.text()
        css = await client.get("/static/style.css")
        assert css.status == 200
    finally:
        await client.close()
