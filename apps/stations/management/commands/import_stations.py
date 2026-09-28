"""Management command: ``python manage.py import_stations <csv>``.

Runs the offline import pipeline once and replaces the station table atomically, so
running it again with the same inputs always yields the same database state.
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.routing.services.geocoding import NominatimClient
from apps.routing.services.http_session import build_http_session
from apps.stations.gazetteer import Coordinates, load_gazetteer
from apps.stations.importer import (
    GeocodedStation,
    ImportSummary,
    PlaceGeocoder,
    PlaceSearch,
    prepare_stations,
)
from apps.stations.models import Station
from apps.stations.repository import StationRepository


class Command(BaseCommand):
    help = "Import fuel stations from the OPIS CSV, geocoding each city at city level."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("csv_path", type=Path)
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Never call Nominatim; use only the gazetteer and the geocode cache.",
        )

    def handle(self, *args: object, **options: object) -> None:
        csv_path = Path(str(options["csv_path"]))
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")
        geocoder = PlaceGeocoder(
            load_gazetteer(settings.GAZETTEER_PATH),
            settings.GEOCODE_CACHE_PATH,
            None if options["offline"] else build_remote_search(),
        )
        try:
            stations, summary = prepare_stations(csv_path, geocoder)
        finally:
            geocoder.save_cache()
        replace_stations(stations)
        StationRepository.instance().reset()
        self._print_summary(summary)

    def _print_summary(self, summary: ImportSummary) -> None:
        lines = [
            f"Rows read:              {summary.rows_read}",
            f"Invalid rows:           {summary.invalid_rows}",
            f"Canadian rows dropped:  {summary.canadian_rows_dropped}",
            f"Other non-contiguous:   {summary.other_rows_dropped}",
            f"Duplicates merged:      {summary.duplicates_merged}",
            f"Stations imported:      {summary.stations_imported}",
            f"Stations skipped:       {summary.stations_skipped}",
            f"Place geocode sources:  {summary.geocode_sources}",
        ]
        self.stdout.write(self.style.SUCCESS("\n".join(lines)))


def build_remote_search() -> PlaceSearch:
    client = NominatimClient(
        build_http_session(settings.HTTP_USER_AGENT, settings.HTTP_CONNECT_RETRIES),
        settings.NOMINATIM_URL,
        settings.NOMINATIM_TIMEOUT_SECONDS,
        settings.NOMINATIM_MIN_INTERVAL_SECONDS,
    )

    def search(city: str, state: str) -> Coordinates | None:
        point = client.search_place(city, state)
        return (point.lat, point.lng) if point else None

    return search


def to_model(geocoded: GeocodedStation) -> Station:
    row = geocoded.row
    return Station(
        opis_id=row.opis_id,
        name=row.name,
        address=row.address,
        city=row.city,
        state=row.state,
        rack_id=row.rack_id,
        retail_price=row.price,
        latitude=geocoded.lat,
        longitude=geocoded.lng,
    )


@transaction.atomic
def replace_stations(stations: list[GeocodedStation]) -> None:
    Station.objects.all().delete()
    Station.objects.bulk_create((to_model(item) for item in stations), batch_size=1000)
