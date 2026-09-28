"""Single orchestrator for a trip request; the API view calls ``TripPlanner.plan`` only.

Flow: resolve both locations, look the trip up in the cache by rounded coordinates, and
on a miss call OSRM exactly once, find stations in the corridor, run the fuel optimizer
and cache the rendered payload under a deterministic ``route_id``. Collaborators are
injected so tests can substitute fakes for the geocoder, router, repository or cache.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from apps.routing.domain.entities import GeoPoint, ResolvedLocation, Route, RouteStation, Vehicle
from apps.routing.domain.exceptions import NoStationNearOriginError
from apps.routing.services.corridor import (
    find_corridor_stations,
    find_origin_stations,
    merge_candidates,
)
from apps.routing.services.fuel_optimizer import optimize_fuel_stops
from apps.routing.services.geocoding import KeyValueCache
from apps.routing.services.route_geometry import RouteTrack, build_track, simplify_polyline
from apps.routing.services.trip_presenter import (
    COORDINATE_DECIMALS,
    METERS_PER_MILE,
    TripResult,
    build_payload,
)
from apps.stations.repository import StationIndex, StationRepository

logger = logging.getLogger(__name__)

ROUTE_ID_LENGTH = 12
TRIP_CACHE_PREFIX = "trip"


class Geocoder(Protocol):
    def resolve(self, query: str) -> ResolvedLocation: ...


class Router(Protocol):
    def route(self, start: GeoPoint, finish: GeoPoint) -> Route: ...


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    vehicle: Vehicle
    starting_fuel_gallons: float
    corridor_miles: float
    origin_search_miles: float
    simplify_tolerance: float
    cache_ttl_seconds: int
    coordinate_precision: int


def trip_cache_key(route_id: str) -> str:
    return f"{TRIP_CACHE_PREFIX}:{route_id}"


class TripPlanner:
    def __init__(
        self,
        geocoder: Geocoder,
        router: Router,
        repository: StationRepository,
        cache: KeyValueCache,
        config: PlannerConfig,
    ) -> None:
        self._geocoder = geocoder
        self._router = router
        self._repository = repository
        self._cache = cache
        self._config = config

    def plan(self, start_query: str, finish_query: str) -> dict[str, Any]:
        started = time.perf_counter()
        start = self._geocoder.resolve(start_query)
        finish = self._geocoder.resolve(finish_query)
        geocoding_calls = start.external_calls + finish.external_calls
        route_id = self.route_id_for(start.point, finish.point)
        cached = self._cache.get(trip_cache_key(route_id))
        if isinstance(cached, dict):
            payload = self._with_queries(cached, start, finish)
            return self._with_meta(payload, geocoding_calls, cache_hit=True, started=started)
        payload = self._compute(route_id, start, finish)
        self._cache.set(trip_cache_key(route_id), payload, self._config.cache_ttl_seconds)
        return self._with_meta(payload, geocoding_calls + 1, cache_hit=False, started=started)

    def cached_trip(self, route_id: str) -> dict[str, Any] | None:
        cached = self._cache.get(trip_cache_key(route_id))
        return cached if isinstance(cached, dict) else None

    def route_id_for(self, start: GeoPoint, finish: GeoPoint) -> str:
        digits = self._config.coordinate_precision
        rounded = [round(value, digits) for value in (start.lat, start.lng, finish.lat, finish.lng)]
        key = "|".join(f"{value:.{digits}f}" for value in rounded)
        return hashlib.sha256(key.encode()).hexdigest()[:ROUTE_ID_LENGTH]

    def _compute(
        self, route_id: str, start: ResolvedLocation, finish: ResolvedLocation
    ) -> dict[str, Any]:
        route = self._router.route(start.point, finish.point)
        track = build_track(route.coordinates, route.distance_meters / METERS_PER_MILE)
        candidates = self._candidates(track, start.point)
        plan = optimize_fuel_stops(
            candidates, track.length_miles, self._config.vehicle, self._config.starting_fuel_gallons
        )
        logger.info(
            "trip.planned route_id=%s miles=%.1f candidates=%d stops=%d",
            route_id,
            track.length_miles,
            len(candidates),
            len(plan.stops),
        )
        display = self._display_coordinates(track)
        return build_payload(
            TripResult(route_id, start, finish, route, display, plan, self._config.vehicle)
        )

    def _candidates(self, track: RouteTrack, origin: GeoPoint) -> list[RouteStation]:
        index: StationIndex = self._repository.get_index()
        corridor = find_corridor_stations(track, index, self._config.corridor_miles)
        if self._config.starting_fuel_gallons > 0:
            return corridor
        radii = (self._config.corridor_miles, self._config.origin_search_miles)
        at_origin = find_origin_stations(origin, index, radii)
        if not at_origin:
            raise NoStationNearOriginError(
                f"No fuel station within {self._config.origin_search_miles:g} miles of the "
                "start, and the vehicle starts with an empty tank."
            )
        return merge_candidates(at_origin, corridor)

    def _display_coordinates(self, track: RouteTrack) -> list[list[float]]:
        simplified = simplify_polyline(track.lng_lat, self._config.simplify_tolerance)
        return np.round(simplified, COORDINATE_DECIMALS).tolist()

    @staticmethod
    def _with_queries(
        payload: dict[str, Any], start: ResolvedLocation, finish: ResolvedLocation
    ) -> dict[str, Any]:
        updated = copy.copy(payload)
        updated["start"] = {**payload["start"], "query": start.query}
        updated["finish"] = {**payload["finish"], "query": finish.query}
        return updated

    @staticmethod
    def _with_meta(
        payload: dict[str, Any], external_calls: int, *, cache_hit: bool, started: float
    ) -> dict[str, Any]:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        meta = {
            "external_api_calls": external_calls,
            "cache_hit": cache_hit,
            "elapsed_ms": elapsed_ms,
        }
        return {**payload, "meta": meta}
