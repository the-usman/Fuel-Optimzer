from __future__ import annotations

import os
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django

django.setup()

from django.core.cache import cache

from apps.routing.domain.entities import GeoPoint, Route
from apps.routing.services.container import build_trip_planner
from apps.routing.services.trip_planner import Router, TripPlanner
from apps.stations.repository import StationRepository

ROUTES = [
    ("New York, NY", "Los Angeles, CA"),
    ("Chicago, IL", "Denver, CO"),
    ("Seattle, WA", "Miami, FL"),
    ("Dallas, TX", "Atlanta, GA"),
    ("Boston, MA", "San Francisco, CA"),
]

HEADER = (
    f"{'route':38} {'miles':>7} {'stops':>5} {'cost $':>8} {'total ms':>9} "
    f"{'osrm ms':>8} {'server ms':>9} {'calls':>5} {'hit ms':>7} {'hit calls':>9}"
)


@dataclass
class TimedRouter:
    inner: Router
    last_ms: float = 0.0
    history: list[float] = field(default_factory=list)

    def route(self, start: GeoPoint, finish: GeoPoint) -> Route:
        started = time.perf_counter()
        try:
            return self.inner.route(start, finish)
        finally:
            self.last_ms = (time.perf_counter() - started) * 1000
            self.history.append(self.last_ms)


def timed(action: Callable[[], dict]) -> tuple[dict, float]:
    started = time.perf_counter()
    result = action()
    return result, (time.perf_counter() - started) * 1000


def main() -> None:
    cache.clear()
    index_started = time.perf_counter()
    StationRepository.instance().get_index()
    print(f"Station index load: {(time.perf_counter() - index_started) * 1000:.0f} ms\n")
    timer: TimedRouter | None = None

    def wrap(router: Router) -> Router:
        nonlocal timer
        timer = TimedRouter(router)
        return timer

    planner = build_trip_planner(wrap)
    print(HEADER)
    rows = [run_route(planner, timer, start, finish) for start, finish in ROUTES]
    print_summary(rows)


def run_route(planner: TripPlanner, timer: TimedRouter, start: str, finish: str) -> tuple:
    cold, cold_ms = timed(lambda: planner.plan(start, finish))
    osrm_ms = timer.last_ms
    warm, warm_ms = timed(lambda: planner.plan(start, finish))
    server_ms = cold_ms - osrm_ms
    print(
        f"{start + ' -> ' + finish:38} {cold['distance_miles']:>7} "
        f"{cold['totals']['stops']:>5} {cold['totals']['fuel_cost_usd']:>8} "
        f"{cold_ms:>9.0f} {osrm_ms:>8.0f} {server_ms:>9.1f} "
        f"{cold['meta']['external_api_calls']:>5} {warm_ms:>7.2f} "
        f"{warm['meta']['external_api_calls']:>9}"
    )
    return (cold_ms, osrm_ms, server_ms, warm_ms, cold, warm)


def print_summary(rows: list[tuple]) -> None:
    print("\nAverages over", len(rows), "routes")
    print(f"  cache miss total:            {statistics.mean(r[0] for r in rows):8.0f} ms")
    print(f"  of which OSRM round trip:    {statistics.mean(r[1] for r in rows):8.0f} ms")
    print(f"  server time excluding OSRM:  {statistics.mean(r[2] for r in rows):8.1f} ms")
    print(f"  cache hit:                   {statistics.mean(r[3] for r in rows):8.2f} ms")
    miss_calls = statistics.mean(r[4]["meta"]["external_api_calls"] for r in rows)
    hit_calls = statistics.mean(r[5]["meta"]["external_api_calls"] for r in rows)
    print(f"  external calls per miss:     {miss_calls:8.1f}")
    print(f"  external calls per hit:      {hit_calls:8.1f}")


if __name__ == "__main__":
    main()
