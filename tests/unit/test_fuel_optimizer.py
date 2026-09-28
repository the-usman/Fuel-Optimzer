"""Unit tests for the pure greedy fuel optimizer, using handcrafted station lists."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.routing.domain.entities import Vehicle
from apps.routing.domain.exceptions import NoFeasibleRouteError
from apps.routing.services.fuel_optimizer import optimize_fuel_stops
from tests.conftest import at_mile

VEHICLE = Vehicle(range_miles=500, mpg=10)


def purchases(plan) -> list[tuple[float, Decimal]]:
    return [(stop.mile_marker, stop.gallons) for stop in plan.stops]


def test_short_trip_buys_only_the_gallons_needed():
    plan = optimize_fuel_stops([at_mile(0, "3.00")], 200, VEHICLE)

    assert purchases(plan) == [(0, Decimal(20))]
    assert plan.total_cost == Decimal("60.00")


def test_picks_the_cheaper_station_when_two_are_in_range():
    stations = [at_mile(0, "4.00"), at_mile(0, "3.00", opis_id=2)]

    plan = optimize_fuel_stops(stations, 300, VEHICLE)

    assert [stop.station.opis_id for stop in plan.stops] == [2]
    assert plan.total_cost == Decimal("90.00")


def test_buys_just_enough_to_reach_a_cheaper_station_ahead():
    stations = [at_mile(0, "4.00"), at_mile(100, "3.00")]

    plan = optimize_fuel_stops(stations, 550, VEHICLE)

    assert purchases(plan) == [(0, Decimal(10)), (100, Decimal(45))]


def test_fills_up_when_the_current_station_is_cheapest_in_range():
    stations = [at_mile(0, "3.00"), at_mile(300, "4.00"), at_mile(450, "5.00")]

    plan = optimize_fuel_stops(stations, 700, VEHICLE)

    assert purchases(plan) == [(0, Decimal(50)), (300, Decimal(20))]
    assert plan.total_cost == Decimal("230.00")


def test_long_trip_needs_several_stops_and_buys_exactly_distance_over_mpg():
    stations = [at_mile(mile, price) for mile, price in [(0, "3.5"), (450, "3.2"), (900, "3.9")]]
    stations += [at_mile(1300, "3.4"), at_mile(1700, "3.6")]

    plan = optimize_fuel_stops(stations, 2000, VEHICLE)

    assert len(plan.stops) >= 3
    assert plan.total_gallons == Decimal(2000) / Decimal(10)


def test_gap_longer_than_range_raises():
    stations = [at_mile(0, "3.00"), at_mile(100, "3.00"), at_mile(700, "3.00")]

    with pytest.raises(NoFeasibleRouteError) as error:
        optimize_fuel_stops(stations, 900, VEHICLE)

    assert (error.value.gap_start_mile, error.value.gap_end_mile) == (100, 700)


def test_station_exactly_one_full_range_ahead_is_reachable():
    stations = [at_mile(0, "3.00"), at_mile(500, "3.00")]

    plan = optimize_fuel_stops(stations, 1000, VEHICLE)

    assert purchases(plan) == [(0, Decimal(50)), (500, Decimal(50))]


def test_destination_exactly_one_full_range_away_needs_one_full_tank():
    plan = optimize_fuel_stops([at_mile(0, "3.00")], 500, VEHICLE)

    assert purchases(plan) == [(0, Decimal(50))]


def test_empty_tank_without_station_at_origin_raises():
    with pytest.raises(NoFeasibleRouteError) as error:
        optimize_fuel_stops([at_mile(5, "3.00")], 100, VEHICLE)

    assert error.value.gap_start_mile == 0


def test_starting_fuel_covers_short_trip_without_stops():
    plan = optimize_fuel_stops([], 300, VEHICLE, starting_fuel_gallons=50)

    assert plan.stops == ()
    assert plan.total_cost == Decimal(0)


def test_starting_fuel_is_used_before_buying():
    plan = optimize_fuel_stops([at_mile(100, "3.00")], 600, VEHICLE, starting_fuel_gallons=20)

    assert purchases(plan) == [(100, Decimal(40))]


def test_stations_off_the_route_range_are_ignored():
    stations = [at_mile(-1, "1.00"), at_mile(0, "3.00"), at_mile(250, "1.00", opis_id=9)]

    plan = optimize_fuel_stops(stations, 200, VEHICLE)

    assert purchases(plan) == [(0, Decimal(20))]


def test_equal_prices_prefer_the_farthest_station():
    stations = [at_mile(0, "3.00"), at_mile(200, "3.00"), at_mile(400, "3.00")]

    plan = optimize_fuel_stops(stations, 800, VEHICLE)

    assert purchases(plan) == [(0, Decimal(50)), (400, Decimal(30))]


def test_total_cost_is_exact_decimal_sum_of_stop_costs():
    stations = [at_mile(0, "3.00733333"), at_mile(333.3, "2.68700001")]

    plan = optimize_fuel_stops(stations, 777.7, VEHICLE)

    assert plan.total_cost == sum(stop.cost for stop in plan.stops)
    assert all(isinstance(stop.cost, Decimal) for stop in plan.stops)
    assert plan.stops[0].cost == Decimal("33.33") * Decimal("3.00733333")
    assert plan.stops[1].cost == Decimal("44.44") * Decimal("2.68700001")
