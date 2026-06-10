# Presence Dashboard Server + HTTP Reporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live web dashboard showing one card per screen with person icons coloured by motion, fed by an `HttpReporter` plugin that POSTs each sensor's presence data + screen name to an aiohttp server.

**Architecture:** Reporters POST `{screen, report}` to `POST /api/report`; a pure `ScreenRegistry` holds latest state per screen; an aiohttp app broadcasts changes over a WebSocket to a vanilla-JS dashboard. Optional feature behind a `[server]` extra (`aiohttp`), so the base install stays `pyserial`-only.

**Tech Stack:** Python asyncio, `aiohttp` (server + client + built-in test utilities), `pytest`/`pytest-asyncio` (already configured, `asyncio_mode = auto`), vanilla HTML/CSS/JS.

**Conventions:** metric/24h elsewhere; run `black` on modified `.py`. Use `./venv/bin/pytest` and `git -c user.name='fw' -c user.email='fwautier61@gmail.com' commit`. aiohttp is installed in the venv. Tests needing aiohttp begin with `pytest.importorskip("aiohttp")` so the suite still passes without the extra.

---

## File Structure

```
ld2460/
  reporters/http_reporter.py     # HttpReporter plugin (aiohttp client)
  server/
    __init__.py
    registry.py                  # ScreenRegistry — pure state
    app.py                       # aiohttp app: endpoints, WS broadcast, reaper
    __main__.py                  # ld2460-server entry point
    static/{index.html,app.js,style.css}
tests/
  test_registry.py
  test_http_reporter.py
  test_server.py
  test_frontend.py
  test_cli_http.py
```

---

### Task 1: `ScreenRegistry` (pure state)

**Files:**
- Create: `ld2460/server/__init__.py`
- Create: `ld2460/server/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test** — `tests/test_registry.py`

```python
from ld2460.server.registry import ScreenRegistry


def _report(count):
    return {"count": count, "present": count > 0, "persons": []}


def test_update_and_snapshot_fields():
    r = ScreenRegistry(offline_after=10, drop_after=300)
    r.update("office", _report(2), now=100.0)
    snap = r.snapshot(now=100.0)
    assert len(snap) == 1
    s = snap[0]
    assert s["name"] == "office"
    assert s["report"]["count"] == 2
    assert s["online"] is True
    assert s["last_seen_age"] == 0.0


def test_online_flag_at_boundary():
    r = ScreenRegistry(offline_after=10, drop_after=300)
    r.update("a", _report(1), now=0.0)
    assert r.snapshot(now=10.0)[0]["online"] is True
    assert r.snapshot(now=10.1)[0]["online"] is False


def test_evict_stale_drops_after_drop_after():
    r = ScreenRegistry(offline_after=10, drop_after=300)
    r.update("a", _report(1), now=0.0)
    assert r.evict_stale(now=200.0) == []
    assert r.evict_stale(now=301.0) == ["a"]
    assert r.snapshot(now=301.0) == []


def test_multiple_screens_sorted():
    r = ScreenRegistry()
    r.update("zeta", _report(1), now=0.0)
    r.update("alpha", _report(0), now=0.0)
    assert [s["name"] for s in r.snapshot(now=0.0)] == ["alpha", "zeta"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.server'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/server/__init__.py`:
```python
"""LD2460 presence dashboard server."""
```

`ld2460/server/registry.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_registry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
black ld2460/server/registry.py tests/test_registry.py
git add ld2460/server/ tests/test_registry.py
git commit -m "feat(server): ScreenRegistry pure state"
```

---

### Task 2: `HttpReporter` plugin

**Files:**
- Create: `ld2460/reporters/http_reporter.py`
- Test: `tests/test_http_reporter.py`

- [ ] **Step 1: Write the failing test** — `tests/test_http_reporter.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_http_reporter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.reporters.http_reporter'`

- [ ] **Step 3: Write minimal implementation** — `ld2460/reporters/http_reporter.py`

```python
from __future__ import annotations

import logging

try:
    import aiohttp
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "HttpReporter requires aiohttp. Install with: "
        'pip install "hlk-ld2460-presence[server]"'
    ) from exc

from ..model import PresenceReport
from . import Reporter

log = logging.getLogger(__name__)


class HttpReporter(Reporter):
    """Best-effort reporter that POSTs presence updates to a dashboard server."""

    def __init__(self, url, screen_name, *, session=None, timeout=2.0):
        self._url = url.rstrip("/") + "/api/report"
        self._screen = screen_name
        self._session = session
        self._owns_session = session is None
        self._timeout = timeout

    async def start(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def report(self, report: PresenceReport):
        payload = {"screen": self._screen, "report": report.to_dict()}
        try:
            async with self._session.post(
                self._url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                await resp.read()
        except Exception as exc:  # best-effort: never break the decode loop
            log.warning("HttpReporter POST to %s failed: %s", self._url, exc)

    async def close(self):
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_http_reporter.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
black ld2460/reporters/http_reporter.py tests/test_http_reporter.py
git add ld2460/reporters/http_reporter.py tests/test_http_reporter.py
git commit -m "feat(reporters): HttpReporter posts presence to the dashboard server"
```

---

### Task 3: aiohttp server app (endpoints, WebSocket, reaper)

**Files:**
- Create: `ld2460/server/app.py`
- Create: `ld2460/server/static/index.html` (placeholder; real dashboard in Task 4)
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing test** — `tests/test_server.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ld2460.server.app'`

- [ ] **Step 3: Write minimal implementation**

`ld2460/server/static/index.html` (placeholder — replaced in Task 4):
```html
<!doctype html>
<html><head><meta charset="utf-8"><title>LD2460 Presence</title></head>
<body><div id="screens"></div></body></html>
```

`ld2460/server/app.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_server.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
black ld2460/server/app.py tests/test_server.py
git add ld2460/server/app.py ld2460/server/static/index.html tests/test_server.py
git commit -m "feat(server): aiohttp app with report endpoint, WebSocket, reaper"
```

---

### Task 4: Dashboard frontend

**Files:**
- Modify: `ld2460/server/static/index.html`
- Create: `ld2460/server/static/style.css`
- Create: `ld2460/server/static/app.js`
- Test: `tests/test_frontend.py`

- [ ] **Step 1: Write the failing test** — `tests/test_frontend.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_frontend.py -v`
Expected: FAIL — `/static/app.js` returns 404 (file missing) so the assertion fails.

- [ ] **Step 3: Write the dashboard files**

`ld2460/server/static/index.html` (replace the placeholder):
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LD2460 Presence</title>
    <link rel="stylesheet" href="/static/style.css" />
  </head>
  <body>
    <h1>LD2460 Presence</h1>
    <div id="screens" class="grid"></div>
    <p id="status" class="status">connecting…</p>
    <script src="/static/app.js"></script>
  </body>
</html>
```

`ld2460/server/static/style.css`:
```css
:root { color-scheme: dark; font-family: system-ui, sans-serif; }
body { margin: 1.5rem; background: #14161a; color: #e6e8eb; }
h1 { font-size: 1.2rem; font-weight: 600; }
.grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.card { background: #1e2228; border: 1px solid #2c313a; border-radius: 10px; padding: 1rem; transition: opacity .3s; }
.card.offline { opacity: .45; }
.card h2 { font-size: 1rem; margin: 0 0 .5rem; display: flex; align-items: center; gap: .5rem; }
.dot { width: .6rem; height: .6rem; border-radius: 50%; background: #3ddc84; }
.offline .dot { background: #767b85; }
.monitor { width: 100%; height: 8px; background: #3a4150; border-radius: 3px; margin: .25rem 0 .75rem; }
.people { display: flex; flex-wrap: wrap; gap: .35rem; min-height: 40px; align-items: flex-end; }
.person { width: 26px; height: 34px; }
.person.static { color: #9aa3af; }
.person.approaching { color: #3ddc84; }
.person.moving_away { color: #f5a623; }
.person.unknown { color: #5b6472; }
.count { margin-top: .6rem; font-size: .85rem; color: #aab2bd; }
.empty { color: #767b85; font-style: italic; }
.status { color: #767b85; font-size: .8rem; margin-top: 1.5rem; }
```

`ld2460/server/static/app.js`:
```javascript
const screensEl = document.getElementById("screens");
const statusEl = document.getElementById("status");
const screens = new Map();

function personSvg(motion) {
  const arrow =
    motion === "approaching" ? "▼" : motion === "moving_away" ? "▲" : "";
  return `<div class="person ${motion}" title="${motion}">
    <svg viewBox="0 0 24 34" width="26" height="34" fill="currentColor">
      <circle cx="12" cy="6" r="5"/>
      <rect x="6" y="13" width="12" height="16" rx="5"/>
    </svg>
    <div style="text-align:center;font-size:.7rem;line-height:1">${arrow}</div>
  </div>`;
}

function render() {
  const names = [...screens.keys()].sort();
  screensEl.innerHTML = names
    .map((name) => {
      const s = screens.get(name);
      const persons = (s.report.persons || []);
      const count = s.report.count != null ? s.report.count : persons.length;
      const icons = persons.length
        ? persons.map((p) => personSvg(p.motion || "unknown")).join("")
        : '<span class="empty">no one</span>';
      const sub = s.online
        ? `${count} ${count === 1 ? "person" : "people"} present`
        : `last seen ${s.last_seen_age}s ago`;
      return `<div class="card ${s.online ? "" : "offline"}">
        <h2><span class="dot"></span>${name}</h2>
        <div class="monitor"></div>
        <div class="people">${icons}</div>
        <div class="count">${sub}</div>
      </div>`;
    })
    .join("");
}

function applyScreen(s) {
  screens.set(s.name, s);
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => (statusEl.textContent = "live");
  ws.onclose = () => {
    statusEl.textContent = "reconnecting…";
    setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") {
      screens.clear();
      msg.screens.forEach(applyScreen);
    } else if (msg.type === "screen") {
      applyScreen(msg.screen);
    } else if (msg.type === "drop") {
      screens.delete(msg.name);
    }
    render();
  };
}

connect();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_frontend.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add ld2460/server/static/ tests/test_frontend.py
git commit -m "feat(server): live dashboard frontend (cards, person icons, motion)"
```

---

### Task 5: Server entry point + packaging

**Files:**
- Create: `ld2460/server/__main__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write `ld2460/server/__main__.py`**

```python
from __future__ import annotations

import argparse

from aiohttp import web

from .app import create_app


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ld2460-server", description="LD2460 presence dashboard server"
    )
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8099)
    args = p.parse_args(argv)
    web.run_app(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the extra + entry point to `pyproject.toml`**

In `[project.optional-dependencies]`, add a `server` entry so the block reads:
```toml
[project.optional-dependencies]
test = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
]
server = [
    "aiohttp>=3.9",
]
```

Replace the `[project.scripts]` block with:
```toml
[project.scripts]
ld2460 = "ld2460.__main__:main"
ld2460-server = "ld2460.server.__main__:main"
```

- [ ] **Step 3: Verify the entry point and help work**

```bash
./venv/bin/pip install -e ".[server]" >/dev/null
./venv/bin/python -m ld2460.server --help
```
Expected: usage text listing `--host` and `--port`, exit 0. Also confirm the console script resolves:
`./venv/bin/ld2460-server --help` prints the same usage.

- [ ] **Step 4: Commit**

```bash
git add ld2460/server/__main__.py pyproject.toml
git commit -m "feat(server): ld2460-server entry point + [server] extra"
```

---

### Task 6: CLI integration (`--reporter http`)

**Files:**
- Modify: `ld2460/__main__.py`
- Test: `tests/test_cli_http.py`

- [ ] **Step 1: Write the failing test** — `tests/test_cli_http.py`

```python
import pytest

from ld2460.__main__ import build_reporters, parse_args


def test_http_reporter_needs_server_url():
    with pytest.raises(SystemExit):
        parse_args(["--reporter", "http"])  # no --server-url


def test_screen_name_defaults_to_hostname():
    import socket

    args = parse_args([])
    assert args.screen_name == socket.gethostname()


def test_build_http_reporter():
    pytest.importorskip("aiohttp")
    from ld2460.reporters.http_reporter import HttpReporter

    args = parse_args(
        ["--reporter", "http", "--server-url", "http://x:8099", "--screen-name", "lab"]
    )
    reporters = build_reporters(args)
    assert isinstance(reporters[0], HttpReporter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_cli_http.py -v`
Expected: FAIL — `http` is not yet a valid `--reporter` choice / `--server-url` unknown.

- [ ] **Step 3: Implement** — edit `ld2460/__main__.py`.

Replace the `_REPORTER_FACTORIES` dict and `parse_args`/`build_reporters` with config-aware versions. The new top of the module's reporter handling:
```python
import socket

_REPORTER_CHOICES = ["text", "json", "http"]
```
(Remove the old `_REPORTER_FACTORIES` dict.)

`parse_args` — change the `--reporter` choices and add `--server-url`/`--screen-name`, then validate. The full function:
```python
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ld2460", description="HLK-LD2460 presence decoder"
    )
    p.add_argument("--port", default="/dev/ttyACM0", help="serial device")
    p.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="baud rate (LD2460 default 115200; change only if you reconfigured the module)",
    )
    p.add_argument(
        "--reporter",
        action="append",
        choices=_REPORTER_CHOICES,
        help="output sink (repeatable); default: text",
    )
    p.add_argument(
        "--static-threshold",
        type=float,
        default=0.05,
        help="radial speed (m/s) below which motion is STATIC",
    )
    p.add_argument(
        "--gate",
        type=float,
        default=1.0,
        help="max metres a target may move between frames to stay the same track",
    )
    p.add_argument(
        "--age-out",
        type=float,
        default=0.5,
        help="seconds before an unseen track is dropped",
    )
    p.add_argument(
        "--smoothing",
        type=float,
        default=0.5,
        help="EMA factor in (0, 1] for distance/velocity (lower = steadier, laggier)",
    )
    p.add_argument(
        "--server-url",
        default=None,
        help="dashboard server URL for --reporter http (e.g. http://localhost:8099)",
    )
    p.add_argument(
        "--screen-name",
        default=socket.gethostname(),
        help="screen name sent with --reporter http (default: hostname)",
    )
    p.add_argument(
        "--enable-on-start",
        action="store_true",
        help="send the enable-reporting command before listening",
    )
    args = p.parse_args(argv)
    if not args.reporter:
        args.reporter = ["text"]
    if not 0.0 < args.smoothing <= 1.0:
        p.error("--smoothing must be in the range (0, 1]")
    if "http" in args.reporter and not args.server_url:
        p.error("--reporter http requires --server-url")
    return args
```

`build_reporters` — make it consume `args` and construct each sink:
```python
def build_reporters(args: argparse.Namespace) -> list[Reporter]:
    out: list[Reporter] = []
    for name in args.reporter:
        if name == "text":
            out.append(ConsoleTextReporter())
        elif name == "json":
            out.append(ConsoleJsonReporter())
        elif name == "http":
            from .reporters.http_reporter import HttpReporter

            out.append(HttpReporter(args.server_url, args.screen_name))
    return out
```

In `_amain`, the call site already reads `build_reporters(args.reporter)` — change it to `build_reporters(args)`:
```python
    reporters = build_reporters(args)
```
Remove the now-unused import of the factories dict if present (there is none beyond the two console classes, which stay imported).

- [ ] **Step 4: Run tests**

Run: `./venv/bin/pytest tests/test_cli_http.py tests/test_cli.py -v`
Expected: PASS. (The existing `tests/test_cli.py` calls `build_reporters(["text", "json"])` with a list — update that one test to pass a parsed args object: `build_reporters(parse_args(["--reporter", "text", "--reporter", "json"]))`. Make that edit in `tests/test_cli.py` and keep its assertions.)

- [ ] **Step 5: Commit**

```bash
black ld2460/__main__.py tests/test_cli_http.py tests/test_cli.py
git add ld2460/__main__.py tests/test_cli_http.py tests/test_cli.py
git commit -m "feat(cli): --reporter http with --server-url/--screen-name"
```

---

### Task 7: README + full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a dashboard section to `README.md`**

Insert before the "## Hardware & datasheets" section:
````markdown
## Live dashboard (optional)

A small web dashboard can show every sensor's presence live — one card per
screen with person icons coloured by motion (approaching / moving away / static).
Needs the `server` extra (`aiohttp`):

```bash
pip install -e ".[server]"          # or "hlk-ld2460-presence[server]"

# 1. start the dashboard
ld2460-server --port 8099           # open http://localhost:8099

# 2. point a sensor at it (one per screen)
ld2460 --reporter http --server-url http://localhost:8099 --screen-name "office"
```

Screens auto-register on first report and grey out when a sensor goes silent.
`--reporter http` can be combined with `text`/`json`.
````

- [ ] **Step 2: Run the full suite**

Run: `./venv/bin/pytest -q`
Expected: all pass — the prior 59 plus the new server/reporter/cli tests (registry 4, http_reporter 2, server 3, frontend 1, cli_http 3 = 13 new) → 72.

- [ ] **Step 3: Format check + smoke the server end to end**

```bash
black --check ld2460 tests
```
Expected: "All done!".

Smoke (manual, optional): in one shell `./venv/bin/ld2460-server --port 8099`, then
`curl -s -XPOST localhost:8099/api/report -H 'content-type: application/json' -d '{"screen":"demo","report":{"count":2,"present":true,"persons":[{"id":1,"motion":"approaching"},{"id":2,"motion":"static"}]}}' -o /dev/null -w '%{http_code}\n'`
Expected: `204`, and the card appears at `http://localhost:8099`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the live presence dashboard"
```

---

## Self-Review Notes

- **Spec coverage:** `HttpReporter` (best-effort POST, owns/injected session) → Task 2; `ScreenRegistry` (update/snapshot/evict, online boundary) → Task 1; server endpoints + WS broadcast + reaper → Task 3; auto-register + offline/drop → Tasks 1+3; dashboard cards/icons/motion colours → Task 4; `ld2460-server` entry + `[server]` extra → Task 5; CLI `--reporter http`/`--server-url`/`--screen-name` + hostname default + validation → Task 6; README → Task 7; tests per component → every task.
- **Type/name consistency:** `ScreenRegistry.update(screen, report, now) -> dict`, `.snapshot(now) -> list[dict]`, `.evict_stale(now) -> list[str]`; `create_app(registry=None, *, clock, reaper_interval)`; WS message types `state`/`screen`/`drop` are produced by `app.py` and consumed by `app.js`; the POST body shape `{screen, report}` matches between `HttpReporter`, `handle_report`, and the tests; `build_reporters(args)` is updated at its only call site in `_amain`.
- **aiohttp-optional:** every aiohttp-touching test starts with `pytest.importorskip("aiohttp")`; the suite stays green without the extra (the import-error path in `http_reporter.py` is `# pragma: no cover`).
- **Existing test touched:** `tests/test_cli.py`'s `build_reporters` call changes from a name list to a parsed-args object (Task 6, Step 4) — the only modification to prior tests.
- **Not automated:** real browser rendering of the dashboard (the JS is covered only by asset-serving + a manual smoke).
