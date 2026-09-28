"""Tests for the health endpoint."""

from __future__ import annotations

import pytest

from apps.stations.repository import StationRepository

pytestmark = pytest.mark.django_db


def test_health_reports_station_count_before_and_after_index_load(client, route_stations):
    before = client.get("/api/v1/health/").json()
    StationRepository.instance().get_index()
    after = client.get("/api/v1/health/").json()

    assert before == {
        "status": "ok",
        "station_count": 8,
        "index_loaded": False,
        "indexed_station_count": 0,
    }
    assert after["index_loaded"] is True
    assert after["indexed_station_count"] == 8
