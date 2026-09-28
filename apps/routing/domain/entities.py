"""Immutable domain entities shared by the routing services.

These dataclasses carry no Django or HTTP dependencies so the core logic (geometry,
corridor search, fuel optimization) can be unit tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class ResolvedLocation:
    query: str
    point: GeoPoint
    source: str
    external_calls: int


@dataclass(frozen=True, slots=True)
class Station:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    lat: float
    lng: float
    price_per_gallon: Decimal


@dataclass(frozen=True, slots=True)
class RouteStation:
    station: Station
    mile_marker: float


@dataclass(frozen=True, slots=True)
class Route:
    coordinates: tuple[tuple[float, float], ...]
    distance_meters: float
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class Vehicle:
    range_miles: float
    mpg: float

    @property
    def tank_gallons(self) -> float:
        return self.range_miles / self.mpg


@dataclass(frozen=True, slots=True)
class FuelStop:
    sequence: int
    station: Station
    mile_marker: float
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class FuelPlan:
    stops: tuple[FuelStop, ...]

    @property
    def total_gallons(self) -> Decimal:
        return sum((stop.gallons for stop in self.stops), Decimal(0))

    @property
    def total_cost(self) -> Decimal:
        return sum((stop.cost for stop in self.stops), Decimal(0))


@dataclass(frozen=True, slots=True)
class ServiceArea:
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float
    states: frozenset[str]

    def contains(self, point: GeoPoint) -> bool:
        return (
            self.min_lat <= point.lat <= self.max_lat and self.min_lng <= point.lng <= self.max_lng
        )
