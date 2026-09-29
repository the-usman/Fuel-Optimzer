
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from apps.routing.domain.entities import GeoPoint, Route
from apps.routing.domain.exceptions import (
    NoRouteFoundError,
    RoutingProviderError,
    RoutingTimeoutError,
)

logger = logging.getLogger(__name__)

NO_ROUTE_CODES = frozenset({"NoRoute", "NoSegment"})


class OsrmClient:
    def __init__(
        self, session: requests.Session, base_url: str, profile: str, timeout_seconds: float
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._profile = profile
        self._timeout = timeout_seconds

    def build_url(self, start: GeoPoint, finish: GeoPoint) -> str:
        waypoints = f"{start.lng},{start.lat};{finish.lng},{finish.lat}"
        return f"{self._base_url}/route/v1/{self._profile}/{waypoints}"

    def route(self, start: GeoPoint, finish: GeoPoint) -> Route:
        url = self.build_url(start, finish)
        started = time.perf_counter()
        payload = self._fetch(url)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("osrm.route url=%s elapsed_ms=%.1f", url, elapsed_ms)
        return self._parse(payload)

    def _fetch(self, url: str) -> dict[str, Any]:
        params = {"overview": "full", "geometries": "geojson"}
        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
        except requests.Timeout as exc:
            raise RoutingTimeoutError("The routing provider timed out.") from exc
        except requests.RequestException as exc:
            raise RoutingProviderError("The routing provider could not be reached.") from exc
        return self._decode(response)

    @staticmethod
    def _decode(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RoutingProviderError("The routing provider returned invalid JSON.") from exc
        code = payload.get("code") if isinstance(payload, dict) else None
        if code in NO_ROUTE_CODES:
            raise NoRouteFoundError("No drivable route exists between these locations.")
        if response.status_code != requests.codes.ok or code != "Ok":
            raise RoutingProviderError(
                f"The routing provider failed (status {response.status_code}, code {code})."
            )
        return payload

    @staticmethod
    def _parse(payload: dict[str, Any]) -> Route:
        try:
            best = payload["routes"][0]
            coordinates = tuple(
                (float(lng), float(lat)) for lng, lat in best["geometry"]["coordinates"]
            )
            return Route(coordinates, float(best["distance"]), float(best["duration"]))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RoutingProviderError(
                "The routing provider returned an unexpected shape."
            ) from exc
