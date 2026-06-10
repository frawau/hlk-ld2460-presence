from __future__ import annotations

import asyncio
import json
import os
import time

from aiohttp import web

from .registry import ScreenRegistry

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def create_app(registry=None, *, clock=time.monotonic, reaper_interval=3.0):
    app = web.Application()
    app["registry"] = registry if registry is not None else ScreenRegistry()
    app["clock"] = clock
    app["ws_clients"] = set()
    app["reaper_interval"] = reaper_interval

    app.router.add_post("/api/report", handle_report)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/", handle_index)
    app.router.add_static("/static/", STATIC_DIR)

    app.on_startup.append(_start_reaper)
    app.on_cleanup.append(_stop_reaper)
    return app


async def _broadcast(app, msg: dict):
    data = json.dumps(msg)
    for ws in list(app["ws_clients"]):
        try:
            await ws.send_str(data)
        except Exception:
            app["ws_clients"].discard(ws)


async def handle_report(request):
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")
    screen = body.get("screen")
    report = body.get("report")
    if not isinstance(screen, str) or not isinstance(report, dict):
        return web.Response(status=400, text="missing screen/report")
    now = request.app["clock"]()
    state = request.app["registry"].update(screen, report, now)
    await _broadcast(request.app, {"type": "screen", "screen": state})
    return web.Response(status=204)


async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    app = request.app
    app["ws_clients"].add(ws)
    now = app["clock"]()
    await ws.send_str(
        json.dumps({"type": "state", "screens": app["registry"].snapshot(now)})
    )
    try:
        async for _msg in ws:
            pass  # no client->server messages expected
    finally:
        app["ws_clients"].discard(ws)
    return ws


async def handle_index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def _reaper(app):
    try:
        while True:
            await asyncio.sleep(app["reaper_interval"])
            now = app["clock"]()
            for name in app["registry"].evict_stale(now):
                await _broadcast(app, {"type": "drop", "name": name})
            await _broadcast(
                app, {"type": "state", "screens": app["registry"].snapshot(now)}
            )
    except asyncio.CancelledError:
        pass


async def _start_reaper(app):
    app["reaper_task"] = asyncio.create_task(_reaper(app))


async def _stop_reaper(app):
    app["reaper_task"].cancel()
    try:
        await app["reaper_task"]
    except asyncio.CancelledError:
        pass
