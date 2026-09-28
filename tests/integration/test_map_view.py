"""Tests for the Leaflet map page, which must render purely from the cache."""

from __future__ import annotations

import pytest
import responses

from tests.integration.test_route_endpoint import FINISH, OSRM_URL, START, URL

pytestmark = pytest.mark.django_db


def test_map_renders_cached_route_without_external_calls(client, route_stations, osrm_payload):
    with responses.RequestsMock() as mocked:
        mocked.get(OSRM_URL, json=osrm_payload)
        body = client.get(URL, {"start": START, "finish": FINISH}).json()

    with responses.RequestsMock(assert_all_requests_are_fired=False) as mocked:
        response = client.get(f"/map/{body['route_id']}/")
        assert len(mocked.calls) == 0

    html = response.content.decode()
    assert response.status_code == 200
    assert "leaflet" in html
    assert '"LineString"' in html
    assert body["fuel_stops"][0]["name"] in html


def test_unknown_route_id_returns_404(client):
    assert client.get("/map/doesnotexist/").status_code == 404
