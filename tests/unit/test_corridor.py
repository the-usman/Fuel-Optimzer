"""Unit tests for the corridor search and the origin station lookup."""

from __future__ import annotations

import numpy as np
import pytest

from apps.routing.domain.entities import GeoPoint
from apps.routing.services.corridor import (
    find_corridor_stations,
    find_origin_stations,
    merge_candidates,
)
from apps.routing.services.route_geometry import build_track
from apps.stations.repository import StationIndex, StationRepository
from tests.conftest import make_station

LATITUDE = 40.0
MILES_PER_DEGREE_LNG = 69.17 * np.cos(np.radians(LATITUDE))
MILES_PER_DEGREE_LAT = 69.05


@pytest.fixture
def straight_track():
    lngs = np.linspace(-100.0, -95.0, 400)
    return build_track(np.column_stack((lngs, np.full_like(lngs, LATITUDE))))


def station_north_of(opis_id: int, lng: float, miles_north: float):
    return make_station(opis_id, "3.00", lat=LATITUDE + miles_north / MILES_PER_DEGREE_LAT, lng=lng)


def test_includes_stations_inside_and_excludes_outside(straight_track):
    index = StationIndex.build(
        [
            station_north_of(1, -99.0, 2.0),
            station_north_of(2, -97.0, 9.0),
            station_north_of(3, -98.0, 15.0),
            station_north_of(4, -90.0, 0.0),
        ]
    )

    found = find_corridor_stations(straight_track, index, corridor_miles=10)

    assert [item.station.opis_id for item in found] == [1, 2]


def test_assigns_mile_marker_of_nearest_route_point(straight_track):
    index = StationIndex.build([station_north_of(1, -98.0, 1.0)])

    (found,) = find_corridor_stations(straight_track, index, corridor_miles=10)

    expected = 2.0 * MILES_PER_DEGREE_LNG
    assert found.mile_marker == pytest.approx(expected, rel=0.01)


def test_empty_index_returns_no_candidates(straight_track):
    assert find_corridor_stations(straight_track, StationIndex.build([]), 10) == []


def test_origin_search_widens_until_a_station_is_found():
    index = StationIndex.build([station_north_of(7, -100.0, 25.0)])
    origin = GeoPoint(LATITUDE, -100.0)

    found = find_origin_stations(origin, index, radii_miles=(10, 40))

    assert [(item.station.opis_id, item.mile_marker) for item in found] == [(7, 0.0)]
    assert find_origin_stations(origin, index, radii_miles=(10,)) == []


def test_merge_prefers_origin_version_of_a_station(straight_track):
    index = StationIndex.build([station_north_of(1, -100.0, 1.0)])
    corridor = find_corridor_stations(straight_track, index, 10)
    origin = find_origin_stations(GeoPoint(LATITUDE, -100.0), index, (10,))

    merged = merge_candidates(origin, corridor)

    assert [(item.station.opis_id, item.mile_marker) for item in merged] == [(1, 0.0)]


def test_repository_loads_once_and_can_be_reset():
    calls = []

    def loader():
        calls.append(1)
        return [make_station(1, "3.00")]

    repository = StationRepository(loader)

    assert not repository.is_loaded
    assert len(repository.get_index()) == 1
    assert repository.get_index() is repository.get_index()
    assert len(calls) == 1
    repository.reset()
    assert not repository.is_loaded
