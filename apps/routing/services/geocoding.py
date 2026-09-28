"""Turns user supplied location strings into coordinates inside the contiguous USA.

Resolution order keeps external calls to a minimum:

1. ``"lat,lng"`` is parsed directly (no lookup at all).
2. ``"City, ST"`` is looked up in the offline Census gazetteer (no network).
3. Anything else, or a gazetteer miss, falls back to one Nominatim search restricted to
   the USA. Nominatim answers are cached so repeating a query costs nothing.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Protocol

import requests

from apps.routing.domain.entities import GeoPoint, ResolvedLocation, ServiceArea
from apps.routing.domain.exceptions import (
    GeocodingProviderError,
    GeocodingTimeoutError,
    InvalidLocationError,
    LocationNotFoundError,
    OutsideServiceAreaError,
)
from apps.stations.gazetteer import Gazetteer

logger = logging.getLogger(__name__)

_LAT_LNG_PATTERN = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$")
_CITY_STATE_PATTERN = re.compile(r"^\s*(?P<city>[^,]+?)\s*,\s*(?P<state>[A-Za-z]{2})\s*$")
_MAX_ABS_LAT = 90.0
_MAX_ABS_LNG = 180.0


class KeyValueCache(Protocol):
    def get(self, key: str, default: object = None) -> object: ...

    def set(self, key: str, value: object, timeout: int | None = None) -> None: ...


def parse_lat_lng(text: str) -> GeoPoint | None:
    match = _LAT_LNG_PATTERN.match(text)
    if match is None:
        return None
    lat, lng = float(match.group(1)), float(match.group(2))
    if abs(lat) > _MAX_ABS_LAT or abs(lng) > _MAX_ABS_LNG:
        raise InvalidLocationError(f"'{text}' is not a valid latitude,longitude pair.")
    return GeoPoint(lat=lat, lng=lng)


def parse_city_state(text: str) -> tuple[str, str] | None:
    match = _CITY_STATE_PATTERN.match(text)
    if match is None:
        return None
    return match.group("city"), match.group("state").upper()


class NominatimClient:
    def __init__(
        self,
        session: requests.Session,
        search_url: str,
        timeout_seconds: float,
        min_interval_seconds: float = 0.0,
    ) -> None:
        self._session = session
        self._search_url = search_url
        self._timeout = timeout_seconds
        self._min_interval = min_interval_seconds
        self._lock = threading.Lock()
        self._last_call = 0.0

    def search(self, query: str) -> GeoPoint | None:
        return self._search({"q": query})

    def search_place(self, city: str, state: str) -> GeoPoint | None:
        return self._search({"city": city, "state": state, "country": "USA"})

    def _search(self, criteria: dict[str, str]) -> GeoPoint | None:
        params = {**criteria, "format": "jsonv2", "countrycodes": "us", "limit": 1}
        self._respect_rate_limit()
        started = time.perf_counter()
        payload = self._get_json(params)
        logger.info(
            "nominatim.search criteria=%r results=%d elapsed_ms=%.1f",
            criteria,
            len(payload),
            (time.perf_counter() - started) * 1000,
        )
        if not payload:
            return None
        return GeoPoint(lat=float(payload[0]["lat"]), lng=float(payload[0]["lon"]))

    def _get_json(self, params: dict[str, object]) -> list[dict[str, str]]:
        try:
            response = self._session.get(self._search_url, params=params, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise GeocodingTimeoutError("The geocoding provider timed out.") from exc
        except (requests.RequestException, ValueError) as exc:
            raise GeocodingProviderError("The geocoding provider request failed.") from exc

    def _respect_rate_limit(self) -> None:
        with self._lock:
            wait = self._last_call + self._min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()


class LocationResolver:
    def __init__(
        self,
        gazetteer: Gazetteer,
        nominatim: NominatimClient,
        service_area: ServiceArea,
        cache: KeyValueCache | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self._gazetteer = gazetteer
        self._nominatim = nominatim
        self._area = service_area
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds

    def resolve(self, query: str) -> ResolvedLocation:
        resolved = self._resolve_locally(query) or self._resolve_remotely(query)
        if not self._area.contains(resolved.point):
            raise OutsideServiceAreaError(f"'{query}' is outside the contiguous USA.")
        return resolved

    def _resolve_locally(self, query: str) -> ResolvedLocation | None:
        point = parse_lat_lng(query)
        if point is not None:
            return ResolvedLocation(query, point, "coordinates", 0)
        city_state = parse_city_state(query)
        if city_state is None:
            return None
        city, state = city_state
        if state not in self._area.states:
            raise OutsideServiceAreaError(f"'{query}' is outside the contiguous USA.")
        coordinates = self._gazetteer.lookup(city, state)
        if coordinates is None:
            return None
        return ResolvedLocation(query, GeoPoint(*coordinates), "gazetteer", 0)

    def _resolve_remotely(self, query: str) -> ResolvedLocation:
        digest = hashlib.sha256(" ".join(query.lower().split()).encode()).hexdigest()
        cache_key = f"geocode:{digest}"
        cached = self._cache.get(cache_key) if self._cache is not None else None
        if isinstance(cached, GeoPoint):
            return ResolvedLocation(query, cached, "nominatim_cache", 0)
        point = self._nominatim.search(query)
        if point is None:
            raise LocationNotFoundError(f"Could not find '{query}' in the USA.")
        if self._cache is not None:
            self._cache.set(cache_key, point, self._cache_ttl)
        return ResolvedLocation(query, point, "nominatim", 1)
