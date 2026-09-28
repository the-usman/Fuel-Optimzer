"""End to end tests of the route endpoint with HTTP mocked at the network boundary."""

from __future__ import annotations

from decimal import Decimal

import pytest
import requests
import responses
from django.conf import settings
from responses import matchers

from apps.stations.models import Station
from tests.conftest import CHICAGO, DENVER

URL = "/api/v1/route/"
OSRM_URL = (
    f"{settings.OSRM_BASE_URL}/route/v1/driving/{CHICAGO[1]},{CHICAGO[0]};{DENVER[1]},{DENVER[0]}"
)
START = f"{CHICAGO[0]},{CHICAGO[1]}"
FINISH = f"{DENVER[0]},{DENVER[1]}"

pytestmark = pytest.mark.django_db


@pytest.fixture
def osrm(osrm_payload):
    with responses.RequestsMock() as mocked:
        mocked.get(OSRM_URL, json=osrm_payload)
        yield mocked


def test_happy_path_returns_full_shape_with_one_external_call(client, route_stations, osrm):
    response = client.get(URL, {"start": START, "finish": FINISH})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "route_id",
        "start",
        "finish",
        "distance_miles",
        "duration_hours",
        "vehicle",
        "fuel_stops",
        "totals",
        "map",
        "meta",
    }
    assert body["meta"] == {**body["meta"], "external_api_calls": 1, "cache_hit": False}
    assert body["distance_miles"] == pytest.approx(1005.1, abs=0.1)
    assert body["vehicle"] == {"range_miles": 500.0, "mpg": 10.0, "tank_gallons": 50.0}
    assert body["totals"]["stops"] == len(body["fuel_stops"]) >= 3
    assert Decimal(body["totals"]["gallons"]) == pytest.approx(
        Decimal("100.51"), abs=Decimal("0.05")
    )
    assert Decimal(body["totals"]["fuel_cost_usd"]) == sum(
        Decimal(s["cost"]) for s in body["fuel_stops"]
    )
    assert body["map"]["html_url"] == f"http://testserver/map/{body['route_id']}/"
    assert len(osrm.calls) == 1


def test_fuel_stops_are_ordered_and_skip_expensive_origin_where_possible(
    client, route_stations, osrm
):
    stops = client.get(URL, {"start": START, "finish": FINISH}).json()["fuel_stops"]

    miles = [stop["mile_marker"] for stop in stops]
    assert miles == sorted(miles)
    assert stops[0]["mile_marker"] == 0
    assert [stop["sequence"] for stop in stops] == list(range(1, len(stops) + 1))
    assert all(stop["opis_id"] != 999 for stop in stops)


def test_geojson_contains_route_line_and_one_point_per_stop(client, route_stations, osrm):
    body = client.get(URL, {"start": START, "finish": FINISH}).json()

    features = body["map"]["geojson"]["features"]
    assert features[0]["geometry"]["type"] == "LineString"
    assert 2 <= len(features[0]["geometry"]["coordinates"]) <= 370
    assert [f["properties"]["sequence"] for f in features[1:]] == [
        stop["sequence"] for stop in body["fuel_stops"]
    ]


def test_second_identical_request_is_a_cache_hit_without_external_calls(
    client, route_stations, osrm
):
    first = client.get(URL, {"start": START, "finish": FINISH}).json()
    second = client.get(URL, {"start": START, "finish": FINISH}).json()

    assert second["meta"]["cache_hit"] is True
    assert second["meta"]["external_api_calls"] == 0
    assert second["fuel_stops"] == first["fuel_stops"]
    assert len(osrm.calls) == 1


def test_city_names_resolve_locally_and_hit_the_cache_by_coordinates(
    client, route_stations, osrm_payload
):
    with responses.RequestsMock() as mocked:
        mocked.get(
            f"{settings.OSRM_BASE_URL}/route/v1/driving/-87.684939,41.837045;-104.881105,39.76185",
            json=osrm_payload,
            match=[matchers.query_param_matcher({"overview": "full", "geometries": "geojson"})],
        )
        first = client.get(URL, {"start": "Chicago, IL", "finish": "Denver, CO"}).json()
        second = client.get(URL, {"start": "chicago,il", "finish": "Denver , co"}).json()

    assert first["meta"]["external_api_calls"] == 1
    assert second["meta"] == {**second["meta"], "cache_hit": True, "external_api_calls": 0}
    assert second["start"]["query"] == "chicago,il"


def test_post_and_get_return_the_same_result(client, route_stations, osrm):
    by_get = client.get(URL, {"start": START, "finish": FINISH}).json()
    by_post = client.post(
        URL, {"start": START, "finish": FINISH}, content_type="application/json"
    ).json()

    for payload in (by_get, by_post):
        payload.pop("meta")
    assert by_post == by_get


def test_missing_params_return_400_in_standard_shape(client):
    response = client.get(URL, {"start": START})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert "finish" in error["details"]


@pytest.mark.parametrize(
    ("start", "code"),
    [("51.5,-0.12", "outside_service_area"), ("95,10", "invalid_location")],
)
def test_bad_locations_return_400(client, start, code):
    response = client.get(URL, {"start": start, "finish": FINISH})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_unknown_city_returns_location_not_found(client):
    with responses.RequestsMock() as mocked:
        mocked.get(settings.NOMINATIM_URL, json=[])
        response = client.get(URL, {"start": "Springfeld, IL", "finish": FINISH})

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "location_not_found",
        "message": "Could not find 'Springfeld, IL' in the USA.",
    }


@pytest.mark.parametrize(
    ("mock_kwargs", "status", "code"),
    [
        ({"body": requests.ReadTimeout()}, 504, "routing_provider_timeout"),
        ({"status": 500, "body": "down"}, 502, "routing_provider_error"),
        ({"status": 400, "json": {"code": "NoRoute"}}, 422, "no_route_found"),
    ],
)
def test_routing_failures_map_to_status_codes(client, route_stations, mock_kwargs, status, code):
    with responses.RequestsMock() as mocked:
        mocked.get(OSRM_URL, **mock_kwargs)
        response = client.get(URL, {"start": START, "finish": FINISH})

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_gap_in_stations_returns_422_with_gap_location(client, route_stations, osrm):
    Station.objects.exclude(opis_id__in=[100, 106]).delete()

    response = client.get(URL, {"start": START, "finish": FINISH})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_feasible_fuel_plan"
    assert error["details"]["gap_start_mile"] == 0


def test_no_station_near_origin_returns_422(client, route_stations, osrm):
    Station.objects.filter(opis_id=100).delete()

    response = client.get(URL, {"start": START, "finish": FINISH})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_station_near_origin"


def test_starting_with_fuel_skips_origin_search(client, route_stations, osrm, settings):
    settings.STARTING_FUEL_GALLONS = 50
    Station.objects.filter(opis_id=100).delete()

    response = client.get(URL, {"start": START, "finish": FINISH})

    assert response.status_code == 200
    assert Decimal(response.json()["totals"]["gallons"]) < Decimal("60")
