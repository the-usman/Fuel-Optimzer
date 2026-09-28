"""Composition root: builds the production ``TripPlanner`` from Django settings once.

Views ask for the planner here instead of constructing collaborators themselves, which
keeps them thin and gives tests a single place to reset or replace the wiring.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from apps.routing.domain.entities import ServiceArea, Vehicle
from apps.routing.services.geocoding import LocationResolver, NominatimClient
from apps.routing.services.http_session import build_http_session
from apps.routing.services.osrm_client import OsrmClient
from apps.routing.services.trip_planner import PlannerConfig, Router, TripPlanner
from apps.stations.gazetteer import CONTIGUOUS_US_STATES, load_gazetteer
from apps.stations.repository import StationRepository


def build_service_area() -> ServiceArea:
    return ServiceArea(**settings.CONTIGUOUS_US_BOUNDS, states=CONTIGUOUS_US_STATES)


def build_planner_config() -> PlannerConfig:
    return PlannerConfig(
        vehicle=Vehicle(range_miles=settings.VEHICLE_RANGE_MILES, mpg=settings.VEHICLE_MPG),
        starting_fuel_gallons=settings.STARTING_FUEL_GALLONS,
        corridor_miles=settings.CORRIDOR_MILES,
        origin_search_miles=settings.ORIGIN_SEARCH_MILES,
        simplify_tolerance=settings.SIMPLIFY_TOLERANCE_DEGREES,
        cache_ttl_seconds=settings.ROUTE_CACHE_TTL_SECONDS,
        coordinate_precision=settings.COORDINATE_CACHE_PRECISION,
    )


def build_trip_planner(wrap_router: Callable[[Router], Router] | None = None) -> TripPlanner:
    session = build_http_session(settings.HTTP_USER_AGENT, settings.HTTP_CONNECT_RETRIES)
    nominatim = NominatimClient(
        session,
        settings.NOMINATIM_URL,
        settings.NOMINATIM_TIMEOUT_SECONDS,
        settings.NOMINATIM_MIN_INTERVAL_SECONDS,
    )
    resolver = LocationResolver(
        load_gazetteer(settings.GAZETTEER_PATH),
        nominatim,
        build_service_area(),
        cache,
        settings.ROUTE_CACHE_TTL_SECONDS,
    )
    router: Router = OsrmClient(
        session, settings.OSRM_BASE_URL, settings.OSRM_PROFILE, settings.OSRM_TIMEOUT_SECONDS
    )
    if wrap_router is not None:
        router = wrap_router(router)
    return TripPlanner(
        resolver, router, StationRepository.instance(), cache, build_planner_config()
    )


@lru_cache(maxsize=1)
def get_trip_planner() -> TripPlanner:
    return build_trip_planner()
