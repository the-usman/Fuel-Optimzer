"""Unit tests for the OSRM client: URL building, parsing and error mapping."""

from __future__ import annotations

import pytest
import requests
import responses
from responses import matchers

from apps.routing.domain.entities import GeoPoint
from apps.routing.domain.exceptions import (
    NoRouteFoundError,
    RoutingProviderError,
    RoutingTimeoutError,
)
from apps.routing.services.http_session import build_http_session
from apps.routing.services.osrm_client import OsrmClient

START = GeoPoint(41.8781, -87.6298)
FINISH = GeoPoint(39.7392, -104.9903)
EXPECTED_URL = "https://osrm.test/route/v1/driving/-87.6298,41.8781;-104.9903,39.7392"


@pytest.fixture
def client() -> OsrmClient:
    return OsrmClient(build_http_session("tests", 0), "https://osrm.test/", "driving", 2.0)


def test_builds_lng_lat_url(client):
    assert client.build_url(START, FINISH) == EXPECTED_URL


@responses.activate
def test_parses_route_response(client, osrm_payload):
    responses.get(
        EXPECTED_URL,
        json=osrm_payload,
        match=[matchers.query_param_matcher({"overview": "full", "geometries": "geojson"})],
    )

    route = client.route(START, FINISH)

    assert route.distance_meters == pytest.approx(1617554.9)
    assert route.duration_seconds == pytest.approx(64095.5)
    assert route.coordinates[0] == tuple(osrm_payload["routes"][0]["geometry"]["coordinates"][0])
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize(
    ("mock_kwargs", "expected"),
    [
        ({"body": requests.ReadTimeout()}, RoutingTimeoutError),
        ({"body": requests.ConnectionError()}, RoutingProviderError),
        ({"status": 500, "body": "oops"}, RoutingProviderError),
        ({"status": 503, "json": {"code": "TooBig"}}, RoutingProviderError),
        ({"status": 400, "json": {"code": "NoRoute", "message": "Impossible"}}, NoRouteFoundError),
        ({"status": 200, "json": {"code": "Ok", "routes": []}}, RoutingProviderError),
    ],
)
def test_failures_map_to_domain_errors(client, mock_kwargs, expected):
    responses.get(EXPECTED_URL, **mock_kwargs)

    with pytest.raises(expected):
        client.route(START, FINISH)
