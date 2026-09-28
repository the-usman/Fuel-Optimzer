"""Unit tests for location parsing, gazetteer resolution and the Nominatim fallback."""

from __future__ import annotations

import pytest
import requests
import responses
from django.conf import settings
from django.core.cache import cache

from apps.routing.domain.entities import GeoPoint
from apps.routing.domain.exceptions import (
    GeocodingProviderError,
    GeocodingTimeoutError,
    InvalidLocationError,
    LocationNotFoundError,
    OutsideServiceAreaError,
)
from apps.routing.services.container import build_service_area
from apps.routing.services.geocoding import (
    LocationResolver,
    NominatimClient,
    parse_city_state,
    parse_lat_lng,
)
from apps.routing.services.http_session import build_http_session
from apps.stations.gazetteer import Gazetteer, load_gazetteer, normalize_place_name

NOMINATIM = settings.NOMINATIM_URL


@pytest.fixture
def resolver() -> LocationResolver:
    session = build_http_session("tests", 0)
    nominatim = NominatimClient(session, NOMINATIM, 1.0)
    return LocationResolver(
        load_gazetteer(settings.GAZETTEER_PATH), nominatim, build_service_area(), cache, 60
    )


def test_parses_lat_lng():
    assert parse_lat_lng(" 41.8781, -87.6298 ") == GeoPoint(41.8781, -87.6298)
    assert parse_lat_lng("Chicago, IL") is None


@pytest.mark.parametrize("text", ["91,-87", "41,-181", "-95.5,10"])
def test_rejects_out_of_range_numbers(text):
    with pytest.raises(InvalidLocationError):
        parse_lat_lng(text)


def test_parses_city_state():
    assert parse_city_state("  Saint Louis ,  mo ") == ("Saint Louis", "MO")
    assert parse_city_state("Chicago") is None


@responses.activate
def test_resolves_city_state_from_gazetteer_without_http(resolver):
    resolved = resolver.resolve("Chicago, IL")

    assert resolved.source == "gazetteer"
    assert resolved.external_calls == 0
    assert resolved.point.lat == pytest.approx(41.84, abs=0.1)
    assert len(responses.calls) == 0


@pytest.mark.parametrize(
    ("csv_name", "census_name"),
    [
        ("Saint Louis", "St. Louis city"),
        ("Fort Worth", "Fort Worth city"),
        ("Mc Calla", "McCalla CDP"),
        ("Kansas City", "Kansas City city"),
        ("Canon City", "Cañon City city"),
        ("Nashville", "Nashville-Davidson metropolitan government (balance)"),
    ],
)
def test_gazetteer_normalizes_place_names(csv_name, census_name):
    gazetteer = Gazetteer.from_rows([("TN", census_name, 1.0, 2.0)])

    assert gazetteer.lookup(csv_name, "tn") == (1.0, 2.0)
    assert normalize_place_name("St. Louis") == normalize_place_name("Saint Louis")


@responses.activate
def test_falls_back_to_nominatim_only_when_gazetteer_misses(resolver):
    responses.get(NOMINATIM, json=[{"lat": "38.9", "lon": "-77.0"}])

    resolved = resolver.resolve("1600 Pennsylvania Avenue, Washington")
    again = resolver.resolve("1600 Pennsylvania Avenue, Washington")

    assert resolved.source == "nominatim"
    assert resolved.external_calls == 1
    assert again.external_calls == 0
    assert len(responses.calls) == 1
    assert responses.calls[0].request.params["countrycodes"] == "us"


@responses.activate
def test_unknown_place_raises_not_found(resolver):
    responses.get(NOMINATIM, json=[])

    with pytest.raises(LocationNotFoundError, match="Springfeld"):
        resolver.resolve("Springfeld, IL")


@pytest.mark.parametrize("query", ["51.5074,-0.1278", "Honolulu, HI", "Anchorage, AK"])
def test_rejects_locations_outside_contiguous_usa(resolver, query):
    with pytest.raises(OutsideServiceAreaError):
        resolver.resolve(query)


@responses.activate
def test_nominatim_result_outside_usa_is_rejected(resolver):
    responses.get(NOMINATIM, json=[{"lat": "21.3", "lon": "-157.8"}])

    with pytest.raises(OutsideServiceAreaError):
        resolver.resolve("Waikiki Beach")


@responses.activate
def test_structured_place_search_sends_city_and_state():
    responses.get(NOMINATIM, json=[{"lat": "40.1", "lon": "-75.1"}])
    client = NominatimClient(build_http_session("tests", 0), NOMINATIM, 1.0)

    assert client.search_place("Bensalem", "PA") == GeoPoint(40.1, -75.1)
    assert responses.calls[0].request.params["city"] == "Bensalem"


@responses.activate
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (requests.ConnectTimeout(), GeocodingTimeoutError),
        (requests.ConnectionError(), GeocodingProviderError),
    ],
)
def test_nominatim_failures_map_to_domain_errors(failure, expected):
    responses.get(NOMINATIM, body=failure)
    client = NominatimClient(build_http_session("tests", 0), NOMINATIM, 1.0)

    with pytest.raises(expected):
        client.search("anything")


@responses.activate
def test_nominatim_rate_limit_waits_between_calls(monkeypatch):
    responses.get(NOMINATIM, json=[])
    sleeps = []
    monkeypatch.setattr("apps.routing.services.geocoding.time.sleep", sleeps.append)
    client = NominatimClient(build_http_session("tests", 0), NOMINATIM, 1.0, 5.0)

    client.search("a")
    client.search("b")

    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 5.0
