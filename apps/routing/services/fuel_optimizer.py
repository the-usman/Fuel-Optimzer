from __future__ import annotations


from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from apps.routing.domain.entities import FuelPlan, FuelStop, RouteStation, Vehicle
from apps.routing.domain.exceptions import NoFeasibleRouteError

DISTANCE_EPSILON_MILES = 1e-6
DESTINATION_PRICE = Decimal(0)
GALLON_PRECISION = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class _Node:
    mile: float
    price: Decimal
    stop: RouteStation | None


@dataclass(frozen=True, slots=True)
class _Purchase:
    node: _Node
    miles_of_fuel: float


def optimize_fuel_stops(
    stations: Sequence[RouteStation],
    route_miles: float,
    vehicle: Vehicle,
    starting_fuel_gallons: float = 0.0,
) -> FuelPlan:
    nodes = _build_nodes(stations, route_miles)
    miles = [node.mile for node in nodes]
    fuel = min(starting_fuel_gallons * vehicle.mpg, vehicle.range_miles)
    _require_reachable(0.0, nodes[0].mile, fuel)
    fuel -= nodes[0].mile
    purchases: list[_Purchase] = []
    current = 0
    while nodes[current].stop is not None:
        target = _choose_target(nodes, miles, current, vehicle.range_miles)
        leg = nodes[target].mile - nodes[current].mile
        cheaper_ahead = nodes[target].price < nodes[current].price
        wanted = leg if cheaper_ahead else vehicle.range_miles
        bought = max(0.0, wanted - fuel)
        if bought > DISTANCE_EPSILON_MILES:
            purchases.append(_Purchase(nodes[current], bought))
        fuel = max(0.0, fuel + bought - leg)
        current = target
    return _to_plan(purchases, vehicle)


def _build_nodes(stations: Sequence[RouteStation], route_miles: float) -> list[_Node]:
    on_route = [s for s in stations if 0.0 <= s.mile_marker <= route_miles]
    ordered = sorted(on_route, key=lambda s: (s.mile_marker, s.station.price_per_gallon))
    nodes = [_Node(s.mile_marker, s.station.price_per_gallon, s) for s in ordered]
    nodes.append(_Node(route_miles, DESTINATION_PRICE, None))
    return nodes


def _require_reachable(from_mile: float, to_mile: float, fuel_miles: float) -> None:
    if to_mile - from_mile > fuel_miles + DISTANCE_EPSILON_MILES:
        raise NoFeasibleRouteError(
            f"No fuel stop between mile {from_mile:.1f} and mile {to_mile:.1f}: "
            f"the gap of {to_mile - from_mile:.1f} miles exceeds the available range.",
            gap_start_mile=round(from_mile, 1),
            gap_end_mile=round(to_mile, 1),
        )


def _choose_target(nodes: list[_Node], miles: list[float], current: int, range_miles: float) -> int:
    here = nodes[current]
    limit = bisect_right(miles, here.mile + range_miles + DISTANCE_EPSILON_MILES)
    reachable = range(current + 1, limit)
    if not reachable:
        _require_reachable(here.mile, nodes[current + 1].mile, range_miles)
    for candidate in reachable:
        if nodes[candidate].price < here.price:
            return candidate
    return min(reachable, key=lambda index: (nodes[index].price, -nodes[index].mile))


def _to_plan(purchases: list[_Purchase], vehicle: Vehicle) -> FuelPlan:
    mpg = Decimal(repr(vehicle.mpg))
    stops = []
    for sequence, purchase in enumerate(purchases, start=1):
        gallons = (Decimal(repr(purchase.miles_of_fuel)) / mpg).quantize(GALLON_PRECISION)
        route_station = purchase.node.stop
        stops.append(
            FuelStop(
                sequence=sequence,
                station=route_station.station,
                mile_marker=route_station.mile_marker,
                gallons=gallons,
                cost=gallons * purchase.node.price,
            )
        )
    return FuelPlan(stops=tuple(stops))
