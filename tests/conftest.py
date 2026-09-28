"""Shared pytest fixtures: isolated caches, a small station set on a recorded route."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.cache import cache

from apps.routing.domain.entities import RouteStation, Station
from apps.routing.services.container import get_trip_planner
from apps.stations.models import Station as StationModel
from apps.stations.repository import StationRepository

FIXTURES = Path(__file__).parent / "fixtures"
CHICAGO = (41.8781, -87.6298)
DENVER = (39.7392, -104.9903)


def make_station(opis_id: int, price: str, lat: float = 40.0, lng: float = -90.0) -> Station:
    return Station(
        opis_id=opis_id,
        name=f"STATION {opis_id}",
        address=f"I-80, EXIT {opis_id}",
        city="Testville",
        state="IL",
        lat=lat,
        lng=lng,
        price_per_gallon=Decimal(price),
    )


def at_mile(mile: float, price: str, opis_id: int | None = None) -> RouteStation:
    return RouteStation(make_station(opis_id or int(mile * 10) + 1, price), mile)


@pytest.fixture(autouse=True)
def isolated_state():
    cache.clear()
    StationRepository.instance().reset()
    get_trip_planner.cache_clear()
    yield
    cache.clear()
    StationRepository.instance().reset()
    get_trip_planner.cache_clear()


@pytest.fixture
def osrm_payload() -> dict:
    return json.loads((FIXTURES / "osrm_chicago_denver.json").read_text())


@pytest.fixture
def route_stations(db, osrm_payload) -> list[StationModel]:
    coordinates = osrm_payload["routes"][0]["geometry"]["coordinates"]
    picks = [(0, "3.899"), (60, "3.299"), (120, "3.599"), (180, "3.199"), (240, "3.499")]
    picks += [(300, "3.099"), (369, "3.799")]
    stations = [
        StationModel(
            opis_id=100 + number,
            name=f"ROUTE STOP {number}",
            address=f"I-80, EXIT {index}",
            city="Somewhere",
            state="IA",
            rack_id=1,
            retail_price=Decimal(price),
            latitude=coordinates[index][1],
            longitude=coordinates[index][0],
        )
        for number, (index, price) in enumerate(picks)
    ]
    far_away = StationModel(
        opis_id=999,
        name="FAR AWAY FUEL",
        address="I-10, EXIT 1",
        city="Miami",
        state="FL",
        retail_price=Decimal("1.000"),
        latitude=25.76,
        longitude=-80.19,
    )
    return StationModel.objects.bulk_create([*stations, far_away])
