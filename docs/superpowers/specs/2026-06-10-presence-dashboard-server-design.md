# Presence Dashboard Server + HTTP Reporter — Design

Date: 2026-06-10

## Purpose

A small, fun live dashboard: multiple LD2460 sensors each run an `HttpReporter`
that sends their presence data plus a screen name to a central server; the server
shows a web page with one card per screen, each rendering the number of detected
people as person icons "in front of" a monitor glyph, coloured by motion
(static / approaching / moving away). Screens auto-register on first report.

This rides the existing `Reporter` plugin seam — no change to the decode core.
It is an **optional** feature behind a `[server]` packaging extra, so the base
install stays `pyserial`-only.

## Components

### 1. `HttpReporter` — `ld2460/reporters/http_reporter.py`

A `Reporter` subclass (existing ABC: async `start`/`report`/`close`).

- `HttpReporter(url, screen_name, *, session=None, timeout=2.0)`.
- `start()`: create an `aiohttp.ClientSession` (unless one was injected for tests).
- `report(report)`: `POST <url>/api/report` with JSON
  `{"screen": screen_name, "report": report.to_dict()}`.
- `close()`: close the session (only if it created it).
- **Best-effort:** any client/connection error is caught and logged at warning
  level; it never propagates (a down server must not kill the sensor's decode
  loop). A short `timeout` bounds each POST.
- Importing the module requires `aiohttp`; a clear ImportError message points to
  `pip install "hlk-ld2460-presence[server]"` if missing.

### 2. `ScreenRegistry` — `ld2460/server/registry.py`

Pure, framework-free state. The testable heart of the server.

- `update(screen, report, now)`: store the latest `report` dict + `last_seen`.
- `snapshot(now)`: return a JSON-ready dict of all screens with
  `{name, report, online, last_seen_age}`; `online = (now - last_seen) <=
  offline_after`.
- `evict_stale(now)`: drop screens whose silence exceeds `drop_after`; return the
  list of dropped names.
- Parameters: `offline_after` (default 10 s), `drop_after` (default 300 s).
- No I/O, no clock of its own — `now` is passed in (deterministic tests).

### 3. Server app — `ld2460/server/app.py` + `ld2460/server/__main__.py`

aiohttp application wiring the registry, endpoints, WebSocket broadcast, and a
reaper task.

- `POST /api/report`: validate the JSON body has `screen` (str) and `report`
  (object); call `registry.update`; broadcast the new screen state to all WS
  clients; return `204`. Malformed body → `400`.
- `GET /ws`: register the socket; immediately send the full `snapshot`; then push
  per-screen update messages as they arrive. Deregister on disconnect.
- `GET /`: serve `static/index.html`.
- Static assets served from `ld2460/server/static/` (`/static/...`).
- Background reaper: every few seconds call `registry.evict_stale` and re-derive
  online/offline; broadcast changes so cards grey out / vanish without a report.
- WebSocket messages are JSON: `{"type": "state", "screens": [...]}` (full) and
  `{"type": "screen", "screen": {...}}` (single update) / `{"type": "drop",
  "name": ...}`.
- `__main__.py`: `--host` (default `0.0.0.0`), `--port` (default `8099`), starts
  the app. Console entry point `ld2460-server`.

### 4. Dashboard — `ld2460/server/static/` (vanilla HTML/CSS/JS, no framework)

- `index.html`, `app.js`, `style.css`.
- Connects to `/ws`, keeps a client-side map of screens, renders one **card** per
  screen: title (screen name) + online/offline dot; a monitor glyph; and `count`
  person glyphs in front of it, each coloured + arrowed by motion
  (approaching → toward the screen / green; moving away → / orange; static /
  grey; unknown / pale). A "N people present" / "no one" line, and "last seen Ns
  ago" when offline. Offline cards are greyed.
- Person and monitor icons are inline SVG. Auto-reconnect the WebSocket on drop.

## Data flow

```
sensor → run_pipeline → HttpReporter.report → POST /api/report
       → ScreenRegistry.update → WS broadcast → browser renders cards
reaper task → ScreenRegistry.evict_stale / online recompute → WS broadcast
```

## CLI integration

`ld2460/__main__.py`:
- `--reporter http` selectable (alongside `text`/`json`).
- `--server-url` (e.g. `http://localhost:8099`) and `--screen-name` (default:
  `socket.gethostname()`).
- `build_reporters` becomes config-aware so it can construct
  `HttpReporter(url, name)` when `http` is selected; selecting `http` without
  `--server-url` is a CLI error.

## Error handling

- Reporter: catch and log network/timeout errors; never raise into the pipeline.
- Server: reject malformed POSTs with 400; tolerate WS clients disconnecting mid-
  broadcast (drop them from the set); reaper runs on its own schedule independent
  of traffic.
- Missing `aiohttp` (extra not installed): actionable ImportError on use.

## Testing

- `ScreenRegistry`: unit tests — update + snapshot fields, online flag at the
  `offline_after` boundary, `evict_stale` after `drop_after`, multi-screen
  isolation. Deterministic via injected `now`.
- `HttpReporter`: spin up a tiny aiohttp test server that records the body;
  assert the POSTed JSON has the right `screen` and `report` payload; assert a
  connection error is swallowed (best-effort) and does not raise.
- Server endpoints (aiohttp built-in `TestClient`): `POST /api/report` updates
  state (verified via a follow-up `/ws` snapshot or a state probe); `GET /`
  returns HTML 200; a WS client receives a broadcast after a POST.
- CLI: `--reporter http` with `--server-url`/`--screen-name` builds an
  `HttpReporter`; `http` without a URL errors.
- Frontend JS: not unit-tested (static asset); covered only by the `GET /` smoke.

## Packaging

- `pyproject.toml`: `[project.optional-dependencies] server = ["aiohttp>=3.9"]`;
  `[project.scripts] ld2460-server = "ld2460.server.__main__:main"`.
- Tests that need aiohttp `pytest.importorskip("aiohttp")` so the suite still
  passes where the extra isn't installed.

## File structure

```
ld2460/
  reporters/http_reporter.py     # HttpReporter plugin
  server/
    __init__.py
    registry.py                  # ScreenRegistry (pure state)
    app.py                       # aiohttp app: endpoints, WS, reaper
    __main__.py                  # CLI entry: ld2460-server
    static/
      index.html
      app.js
      style.css
tests/
  test_http_reporter.py
  test_registry.py
  test_server.py
  test_cli_http.py               # or extend test_cli.py
```

## Out of scope

- Auth, HTTPS/TLS, persistence (state is in-memory; restart clears it).
- Historical charts / logging of presence over time.
- A pre-configured screen list (screens auto-register; this can be added later).
- Mobile-specific layout polish beyond a responsive card grid.
