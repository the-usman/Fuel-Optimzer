"""Turns a computed trip into the JSON friendly payload returned by the API and cached.

Rounding happens here and only here. Stop costs are rounded to cents first and the trip
total is the sum of those rounded values, so the numbers a client sees always add up.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.routing.domain.entities import FuelPlan, FuelStop, ResolvedLocation, Route, Vehicle

METERS_PER_MILE = 1609.344
SECONDS_PER_HOUR = 3600
CENTS = Decimal("0.01")
PRICE_PRECISION = Decimal("0.001")
COORDINATE_DECIMALS = 5
MILE_DECIMALS = 1


@dataclass(frozen=True, slots=True)
class TripResult:
    route_id: str
    start: ResolvedLocation
    finish: ResolvedLocation
    route: Route
    display_coordinates: list[list[float]]
    plan: FuelPlan
    vehicle: Vehicle


def money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def build_payload(result: TripResult) -> dict[str, Any]:
    stops = [present_stop(stop) for stop in result.plan.stops]
    return {
        "route_id": result.route_id,
        "start": present_location(result.start),
        "finish": present_location(result.finish),
        "distance_miles": round(result.route.distance_meters / METERS_PER_MILE, MILE_DECIMALS),
        "duration_hours": round(result.route.duration_seconds / SECONDS_PER_HOUR, 1),
        "vehicle": present_vehicle(result.vehicle),
        "fuel_stops": stops,
        "totals": present_totals(result.plan),
        "map": {"geojson": build_geojson(result.display_coordinates, stops)},
    }


def present_location(location: ResolvedLocation) -> dict[str, Any]:
    return {
        "query": location.query,
        "lat": round(location.point.lat, COORDINATE_DECIMALS),
        "lng": round(location.point.lng, COORDINATE_DECIMALS),
    }


def present_vehicle(vehicle: Vehicle) -> dict[str, float]:
    return {
        "range_miles": vehicle.range_miles,
        "mpg": vehicle.mpg,
        "tank_gallons": vehicle.tank_gallons,
    }


def present_stop(stop: FuelStop) -> dict[str, Any]:
    station = stop.station
    return {
        "sequence": stop.sequence,
        "opis_id": station.opis_id,
        "name": station.name,
        "address": station.address,
        "city": station.city,
        "state": station.state,
        "lat": round(station.lat, COORDINATE_DECIMALS),
        "lng": round(station.lng, COORDINATE_DECIMALS),
        "mile_marker": round(stop.mile_marker, MILE_DECIMALS),
        "price_per_gallon": str(station.price_per_gallon.quantize(PRICE_PRECISION)),
        "gallons": str(money(stop.gallons)),
        "cost": str(money(stop.cost)),
    }


def present_totals(plan: FuelPlan) -> dict[str, Any]:
    gallons = sum((money(stop.gallons) for stop in plan.stops), Decimal("0.00"))
    cost = sum((money(stop.cost) for stop in plan.stops), Decimal("0.00"))
    return {"gallons": str(gallons), "fuel_cost_usd": str(cost), "stops": len(plan.stops)}


def build_geojson(coordinates: list[list[float]], stops: list[dict[str, Any]]) -> dict[str, Any]:
    route_feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {"kind": "route"},
    }
    stop_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [stop["lng"], stop["lat"]]},
            "properties": {"kind": "fuel_stop", **stop},
        }
        for stop in stops
    ]
    return {"type": "FeatureCollection", "features": [route_feature, *stop_features]}
