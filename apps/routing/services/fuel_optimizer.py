"""Chooses where to refuel and how much to buy so the whole trip costs as little as possible.

Pure function over plain dataclasses, with no Django imports, so it is trivially testable.

Assumptions:

1. Tank capacity is ``range_miles / mpg`` gallons (500 miles at 10 MPG = 50 gallons).
2. The vehicle starts with ``starting_fuel_gallons`` (0 by default, so the first purchase
   happens at a station at the origin and the total covers the full trip).
3. It should reach the destination with (close to) zero fuel: nothing is bought beyond
   what is needed to finish.
4. Stations are points on the route at their mile marker. The detour from the highway to
   the station is ignored for cost purposes because every station is inside the corridor.
5. Prices are fixed for the duration of the trip.

Algorithm (the classic greedy solution to the "gas station problem", optimal for fixed
prices): the destination is a final node priced at zero. At each station, look at every
node reachable on a full tank. If one of them is cheaper, buy just enough to reach the
first cheaper one and drive there. Otherwise fill the tank and drive to the cheapest
reachable station. Fuel bought here is therefore never more expensive than any fuel that
could have replaced it, which is why the plan is optimal. Complexity is O(n log n) for
the sort plus O(n * k) for the scans, where k is the number of stations within one tank.

Money uses ``Decimal``. Gallons are kept to a millionth of a gallon so float noise in the
mile markers never leaks into prices; costs are exact products of gallons and price and
are rounded to cents only when the response is rendered.
"""

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
