"""Tests for the import_stations management command and its cleaning pipeline."""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
import responses
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.stations.models import Station
from apps.stations.repository import StationRepository
from tests.conftest import FIXTURES

CSV = FIXTURES / "stations_small.csv"


@pytest.fixture
def geocode_cache(tmp_path, settings) -> Path:
    settings.GEOCODE_CACHE_PATH = tmp_path / "geocode_cache.json"
    return settings.GEOCODE_CACHE_PATH


def run_import(*extra: str) -> str:
    output = StringIO()
    call_command("import_stations", str(CSV), *extra, stdout=output)
    return output.getvalue()


def snapshot() -> list[dict]:
    return [
        {key: value for key, value in row.items() if key != "id"}
        for row in Station.objects.order_by("opis_id").values()
    ]


@pytest.mark.django_db
def test_import_cleans_deduplicates_and_is_idempotent(geocode_cache):
    summary = run_import("--offline")
    first = snapshot()
    run_import("--offline")

    assert snapshot() == first
    assert sorted(Station.objects.values_list("opis_id", flat=True)) == [7, 20, 62]
    assert not Station.objects.filter(state="AB").exists()
    pilot = Station.objects.get(opis_id=20)
    assert pilot.retail_price == Decimal("3.599")
    assert pilot.name == "PILOT TRAVEL CENTER #1243"
    assert Station.objects.get(opis_id=7).city == "Big Cabin"
    chicago = Station.objects.get(opis_id=62)
    assert (chicago.city, chicago.state, chicago.rack_id) == ("Chicago", "IL", None)
    assert "Rows read:              7" in summary
    assert "Canadian rows dropped:  1" in summary
    assert "Duplicates merged:      1" in summary
    assert "Stations imported:      3" in summary
    assert "Stations skipped:       1" in summary
    assert "Invalid rows:           1" in summary


@pytest.mark.django_db
@responses.activate
def test_import_falls_back_to_nominatim_once_and_caches_results(geocode_cache):
    responses.get(settings.NOMINATIM_URL, json=[{"lat": "31.5", "lon": "-97.1"}])

    run_import()
    run_import()

    assert len(responses.calls) == 1
    assert json.loads(geocode_cache.read_text()) == {"Notarealplace|TX": [31.5, -97.1]}
    assert Station.objects.get(opis_id=60).latitude == 31.5


@pytest.mark.django_db
def test_import_uses_cached_misses_without_network(geocode_cache):
    geocode_cache.write_text(json.dumps({"Notarealplace|TX": None}))

    summary = run_import()

    assert "Stations skipped:       1" in summary


@pytest.mark.django_db
def test_import_resets_the_in_memory_index(geocode_cache):
    repository = StationRepository.instance()
    repository.get_index()

    run_import("--offline")

    assert not repository.is_loaded


def test_missing_file_is_a_command_error():
    with pytest.raises(CommandError):
        call_command("import_stations", "does-not-exist.csv")


@pytest.mark.django_db
@responses.activate
def test_import_rejects_remote_results_outside_the_requested_state(geocode_cache):
    responses.get(settings.NOMINATIM_URL, json=[{"lat": "32.6", "lon": "-90.0"}])

    summary = run_import()

    assert "Stations skipped:       1" in summary
    assert json.loads(geocode_cache.read_text()) == {"Notarealplace|TX": None}
