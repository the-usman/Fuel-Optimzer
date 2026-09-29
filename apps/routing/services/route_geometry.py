
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

EARTH_RADIUS_MILES = 3958.7613

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class RouteTrack:
    lng_lat: FloatArray
    cumulative_miles: FloatArray
    unit_vectors: FloatArray

    @property
    def length_miles(self) -> float:
        return float(self.cumulative_miles[-1])


def haversine_miles(
    lat1: ArrayLike, lng1: ArrayLike, lat2: ArrayLike, lng2: ArrayLike
) -> FloatArray:
    phi1, lam1, phi2, lam2 = (
        np.radians(np.asarray(v, dtype=float)) for v in (lat1, lng1, lat2, lng2)
    )
    half_chord = (
        np.sin((phi2 - phi1) / 2) ** 2
        + np.cos(phi1) * np.cos(phi2) * np.sin((lam2 - lam1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(half_chord, 0.0, 1.0)))


def cumulative_miles(lng_lat: FloatArray) -> FloatArray:
    lng, lat = lng_lat[:, 0], lng_lat[:, 1]
    segments = haversine_miles(lat[:-1], lng[:-1], lat[1:], lng[1:])
    return np.concatenate(([0.0], np.cumsum(segments)))


def to_unit_vectors(lat: ArrayLike, lng: ArrayLike) -> FloatArray:
    phi = np.radians(np.asarray(lat, dtype=float))
    lam = np.radians(np.asarray(lng, dtype=float))
    cos_phi = np.cos(phi)
    return np.column_stack((cos_phi * np.cos(lam), cos_phi * np.sin(lam), np.sin(phi)))


def miles_to_chord(miles: float) -> float:
    return float(2 * np.sin(miles / (2 * EARTH_RADIUS_MILES)))


def chord_to_miles(chord: ArrayLike) -> FloatArray:
    clipped = np.clip(np.asarray(chord, dtype=float) / 2, 0.0, 1.0)
    return 2 * EARTH_RADIUS_MILES * np.arcsin(clipped)


def build_track(coordinates: ArrayLike, reported_length_miles: float | None = None) -> RouteTrack:
    lng_lat = np.asarray(coordinates, dtype=float).reshape(-1, 2)
    cumulative = cumulative_miles(lng_lat)
    measured = cumulative[-1]
    if reported_length_miles is not None and measured > 0:
        cumulative = cumulative * (reported_length_miles / measured)
    vectors = to_unit_vectors(lng_lat[:, 1], lng_lat[:, 0])
    return RouteTrack(lng_lat=lng_lat, cumulative_miles=cumulative, unit_vectors=vectors)


def sample_by_distance(cumulative: FloatArray, step_miles: float) -> NDArray[np.intp]:
    buckets = np.floor(cumulative / step_miles).astype(np.int64)
    first_in_bucket = np.flatnonzero(np.diff(buckets, prepend=-1))
    return np.union1d(first_in_bucket, [len(cumulative) - 1])


def _line_distances(points: FloatArray, start: FloatArray, end: FloatArray) -> FloatArray:
    dx, dy = end - start
    offsets_x = points[:, 0] - start[0]
    offsets_y = points[:, 1] - start[1]
    length = float(np.hypot(dx, dy))
    if length == 0.0:
        return np.hypot(offsets_x, offsets_y)
    return np.abs(dx * offsets_y - dy * offsets_x) / length


def _thin_by_step(points: FloatArray, step: float) -> FloatArray:
    steps = np.hypot(*np.diff(points, axis=0).T)
    cumulative = np.concatenate(([0.0], np.cumsum(steps)))
    return points[sample_by_distance(cumulative, step)]


def simplify_polyline(points: ArrayLike, tolerance: float) -> FloatArray:
    array = np.asarray(points, dtype=float)
    if len(array) < 3 or tolerance <= 0:
        return array
    array = _thin_by_step(array, tolerance / 2)
    keep = np.zeros(len(array), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(array) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        distances = _line_distances(array[first + 1 : last], array[first], array[last])
        farthest = int(np.argmax(distances))
        if distances[farthest] > tolerance:
            split = first + 1 + farthest
            keep[split] = True
            stack.extend(((first, split), (split, last)))
    return array[keep]
