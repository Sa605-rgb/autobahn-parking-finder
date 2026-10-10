"""HTTP client for the public Autobahn API. No API key is required."""

import asyncio
import logging
from urllib.parse import quote

import httpx

from parking_finder.parse import road_sort_key
from parking_finder.settings import BASE_URL

logger = logging.getLogger("parking_finder")


class AutobahnError(Exception):
    """A failure the UI can show without crashing."""

    def __init__(self, message: str, *, kind: str = "network") -> None:
        super().__init__(message)
        self.kind = kind


class AutobahnClient:
    """Small async wrapper around https://verkehr.autobahn.de/o/autobahn."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        verify: bool = True,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            verify=verify,
            transport=transport,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": "SmartAutobahnParkingFinder/1.0",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> dict:
        try:
            response = await self._client.get(path)
        except httpx.TimeoutException as exc:
            logger.warning("Timeout calling %s", path)
            raise AutobahnError(
                "The Autobahn API timed out. Check your connection and try again.",
                kind="timeout",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Request failed for %s: %s", path, exc.__class__.__name__)
            detail = str(exc).lower()
            if "certificate" in detail or "ssl" in detail:
                raise AutobahnError(
                    "The Autobahn API certificate could not be verified. "
                    "If you are on a company network, set AUTOBAHN_SSL_VERIFY=0 in .env and restart.",
                    kind="ssl",
                ) from exc
            raise AutobahnError(
                "The Autobahn API is unreachable. Check your network and try again.",
                kind="network",
            ) from exc

        if response.status_code in {204, 404}:
            return {}
        if response.status_code >= 400:
            raise AutobahnError(
                f"The Autobahn API returned HTTP {response.status_code}. Try again shortly.",
                kind="http",
            )
        if not response.content or not response.content.strip():
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise AutobahnError(
                "The Autobahn API returned data that is not valid JSON.",
                kind="parse",
            ) from exc
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {"items": payload}
        return {}

    async def list_roads(self) -> list[str]:
        payload = await self._get("/")
        roads = payload.get("roads", payload.get("items", []))
        if not isinstance(roads, list):
            return []
        cleaned = {road.strip() for road in roads if isinstance(road, str) and road.strip()}
        return sorted(cleaned, key=road_sort_key)

    async def parking(self, road: str) -> dict:
        return await self._get(f"/{quote(road)}/services/parking_lorry")

    async def roadworks(self, road: str) -> dict:
        return await self._get(f"/{quote(road)}/services/roadworks")

    async def warnings(self, road: str) -> dict:
        return await self._get(f"/{quote(road)}/services/warning")

    async def closures(self, road: str) -> dict:
        return await self._get(f"/{quote(road)}/services/closure")

    async def webcams(self, road: str) -> dict:
        return await self._get(f"/{quote(road)}/services/webcam")

    async def load_road(self, road: str) -> dict[str, tuple[dict, str | None]]:
        """Fetch every section. One failed call does not discard the others."""

        async def one(key: str, loader) -> tuple[str, dict, str | None]:
            try:
                return key, await loader(road), None
            except AutobahnError as exc:
                return key, {}, str(exc)

        rows = await asyncio.gather(
            one("parking", self.parking),
            one("roadworks", self.roadworks),
            one("warnings", self.warnings),
            one("closures", self.closures),
            one("webcams", self.webcams),
        )
        return {key: (payload, error) for key, payload, error in rows}
