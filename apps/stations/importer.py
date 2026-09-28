"""Offline pipeline that turns the raw OPIS fuel price CSV into geocoded station rows.

Steps: read and clean every row, drop anything outside the contiguous USA (Canadian
provinces in particular), merge duplicate OPIS IDs, then geocode each unique
(city, state) pair once. Geocoding uses the offline Census gazetteer first, then a JSON
cache file, and only then (optionally) Nominatim, whose answers are written back to the
cache so the network is never asked twice about the same place.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from string import capwords

from apps.stations.gazetteer import CONTIGUOUS_US_STATES, Coordinates, Gazetteer

logger = logging.getLogger(__name__)

CANADIAN_PROVINCES: frozenset[str] = frozenset("AB BC MB NB NL NS NT NU ON PE QC SK YT".split())

PlaceSearch = Callable[[str, str], Coordinates | None]


@dataclass(frozen=True, slots=True)
class CsvStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int | None
    price: Decimal


@dataclass(frozen=True, slots=True)
class GeocodedStation:
    row: CsvStation
    lat: float
    lng: float


@dataclass(slots=True)
class ImportSummary:
    rows_read: int = 0
    canadian_rows_dropped: int = 0
    other_rows_dropped: int = 0
    invalid_rows: int = 0
    duplicates_merged: int = 0
    stations_imported: int = 0
    stations_skipped: int = 0
    geocode_sources: dict[str, int] = field(default_factory=dict)


def normalize_city(value: str) -> str:
    city = " ".join(value.split())
    return capwords(city) if city.isupper() or city.islower() else city


def parse_row(raw: dict[str, str]) -> CsvStation:
    fields = {key.strip(): (value or "").strip() for key, value in raw.items() if key}
    rack_id = fields.get("Rack ID", "")
    return CsvStation(
        opis_id=int(fields["OPIS Truckstop ID"]),
        name=" ".join(fields["Truckstop Name"].split()),
        address=" ".join(fields["Address"].split()),
        city=normalize_city(fields["City"]),
        state=fields["State"].upper(),
        rack_id=int(rack_id) if rack_id.isdigit() else None,
        price=Decimal(fields["Retail Price"]),
    )


def read_rows(path: Path, summary: ImportSummary) -> Iterator[CsvStation]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            summary.rows_read += 1
            try:
                yield parse_row(raw)
            except (KeyError, ValueError, InvalidOperation):
                summary.invalid_rows += 1


def filter_contiguous(rows: Iterable[CsvStation], summary: ImportSummary) -> Iterator[CsvStation]:
    for row in rows:
        if row.state in CONTIGUOUS_US_STATES:
            yield row
        elif row.state in CANADIAN_PROVINCES:
            summary.canadian_rows_dropped += 1
        else:
            summary.other_rows_dropped += 1


def merge_duplicate(kept: CsvStation, other: CsvStation) -> CsvStation:
    longest_name = max(kept.name, other.name, key=len)
    cheapest = kept if kept.price <= other.price else other
    return replace(cheapest, name=longest_name)


def deduplicate(rows: Iterable[CsvStation], summary: ImportSummary) -> list[CsvStation]:
    unique: dict[int, CsvStation] = {}
    for row in rows:
        existing = unique.get(row.opis_id)
        if existing is None:
            unique[row.opis_id] = row
        else:
            summary.duplicates_merged += 1
            unique[row.opis_id] = merge_duplicate(existing, row)
    return list(unique.values())


class PlaceGeocoder:
    def __init__(
        self, gazetteer: Gazetteer, cache_path: Path, remote_search: PlaceSearch | None
    ) -> None:
        self._gazetteer = gazetteer
        self._cache_path = cache_path
        self._remote_search = remote_search
        self._cache: dict[str, list[float] | None] = self._load_cache()
        self.sources: dict[str, int] = {}

    def geocode(self, city: str, state: str) -> Coordinates | None:
        found = self._gazetteer.lookup(city, state)
        if found is not None:
            return self._count("gazetteer", found)
        key = f"{city}|{state}"
        if key in self._cache:
            cached = self._cache[key]
            return self._count("cache", (cached[0], cached[1]) if cached else None)
        if self._remote_search is None:
            return self._count("unresolved", None)
        found = self._remote_search(city, state)
        if found is not None and not self._gazetteer.state_contains(state, found):
            logger.warning("import.remote_result_outside_state place=%s coordinates=%s", key, found)
            found = None
        self._cache[key] = list(found) if found else None
        return self._count("nominatim", found)

    def save_cache(self) -> None:
        ordered = dict(sorted(self._cache.items()))
        self._cache_path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")

    def _count(self, source: str, found: Coordinates | None) -> Coordinates | None:
        label = source if found is not None else f"{source}_miss"
        self.sources[label] = self.sources.get(label, 0) + 1
        return found

    def _load_cache(self) -> dict[str, list[float] | None]:
        if not self._cache_path.exists():
            return {}
        return json.loads(self._cache_path.read_text(encoding="utf-8"))


def geocode_stations(
    stations: Iterable[CsvStation], geocoder: PlaceGeocoder, summary: ImportSummary
) -> list[GeocodedStation]:
    places: dict[tuple[str, str], Coordinates | None] = {}
    geocoded: list[GeocodedStation] = []
    for station in stations:
        place = (station.city, station.state)
        if place not in places:
            places[place] = geocoder.geocode(*place)
        coordinates = places[place]
        if coordinates is None:
            summary.stations_skipped += 1
            logger.debug("import.skip opis_id=%s place=%s", station.opis_id, place)
            continue
        geocoded.append(GeocodedStation(station, *coordinates))
    summary.geocode_sources = dict(geocoder.sources)
    return geocoded


def prepare_stations(
    csv_path: Path, geocoder: PlaceGeocoder
) -> tuple[list[GeocodedStation], ImportSummary]:
    summary = ImportSummary()
    rows = filter_contiguous(read_rows(csv_path, summary), summary)
    unique = deduplicate(rows, summary)
    geocoded = geocode_stations(unique, geocoder, summary)
    summary.stations_imported = len(geocoded)
    return geocoded, summary
