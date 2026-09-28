"""Unit tests for haversine distances, mile markers, sampling and Douglas-Peucker."""

from __future__ import annotations

import numpy as np
import pytest

from apps.routing.services.route_geometry import (
    build_track,
    chord_to_miles,
    cumulative_miles,
    haversine_miles,
    miles_to_chord,
    sample_by_distance,
    simplify_polyline,
)


def test_haversine_matches_known_city_pair():
    new_york_to_los_angeles = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)

    assert float(new_york_to_los_angeles) == pytest.approx(2445.6, abs=5)


def test_haversine_of_identical_points_is_zero():
    assert float(haversine_miles(41.0, -87.0, 41.0, -87.0)) == 0.0


def test_cumulative_miles_are_monotonic_and_end_at_route_length(osrm_payload):
    coordinates = np.array(osrm_payload["routes"][0]["geometry"]["coordinates"])

    cumulative = cumulative_miles(coordinates)

    assert cumulative[0] == 0.0
    assert np.all(np.diff(cumulative) >= 0)
    segments = [
        haversine_miles(a[1], a[0], b[1], b[0])
        for a, b in zip(coordinates[:-1], coordinates[1:], strict=True)
    ]
    assert cumulative[-1] == pytest.approx(float(np.sum(segments)))


def test_build_track_scales_to_the_reported_length():
    track = build_track([[-90.0, 40.0], [-89.0, 40.0], [-88.0, 40.0]], reported_length_miles=120)

    assert track.length_miles == pytest.approx(120)
    assert track.cumulative_miles[1] == pytest.approx(60)
    assert track.unit_vectors.shape == (3, 3)


def test_chord_conversion_round_trips():
    assert float(chord_to_miles(miles_to_chord(25.0))) == pytest.approx(25.0)


def test_sampling_keeps_one_vertex_per_step_and_the_last_vertex():
    cumulative = np.array([0.0, 1.0, 4.0, 6.0, 11.0, 12.0])

    assert sample_by_distance(cumulative, 5.0).tolist() == [0, 3, 4, 5]


def test_douglas_peucker_keeps_endpoints_and_reduces_points():
    x = np.linspace(0, 10, 500)
    line = np.column_stack((x, np.sin(x) * 0.001))

    simplified = simplify_polyline(line, tolerance=0.01)

    assert len(simplified) < len(line)
    assert simplified[0].tolist() == line[0].tolist()
    assert simplified[-1].tolist() == line[-1].tolist()


def test_douglas_peucker_keeps_significant_corners():
    corner = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0], [1.0, 1.0]]

    assert simplify_polyline(corner, tolerance=0.1).tolist() == [[0, 0], [1, 0], [1, 1]]


def test_douglas_peucker_handles_duplicate_endpoints_and_short_input():
    loop = [[0.0, 0.0], [1.0, 1.0], [0.0, 0.0]]

    assert len(simplify_polyline(loop, tolerance=0.1)) == 3
    assert len(simplify_polyline([[0.0, 0.0], [1.0, 1.0]], tolerance=0.1)) == 2
