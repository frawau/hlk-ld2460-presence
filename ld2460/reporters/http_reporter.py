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
