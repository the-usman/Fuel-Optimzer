"""Finds fuel stations inside a corridor around a route and assigns their mile markers.

Two stage search that stays fast on routes with tens of thousands of vertices:

1. Coarse: sample the route every ``corridor_miles`` and ask the station KD-tree (built
   once per process) for stations within ``corridor + step`` of any sample. Every vertex
   lies within one step of a sample, so this is a guaranteed superset.
2. Exact: build a KD-tree over the full route and find, for each candidate, its nearest
   route vertex. Candidates farther than the corridor are dropped; the survivors take the
   cumulative mileage of that vertex as their mile marker.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from apps.routing.domain.entities import GeoPoint, RouteStation
from apps.routing.services.route_geometry import (
    RouteTrack,
    chord_to_miles,
    sample_by_distance,
    to_unit_vectors,
)
from apps.stations.repository import StationIndex


def find_corridor_stations(
    track: RouteTrack, index: StationIndex, corridor_miles: float
) -> list[RouteStation]:
    sample_step_miles = corridor_miles
    samples = sample_by_distance(track.cumulative_miles, sample_step_miles)
    candidates = index.within(track.unit_vectors[samples], corridor_miles + sample_step_miles)
    if len(candidates) == 0:
        return []
    chords, nearest = cKDTree(track.unit_vectors).query(index.unit_vectors[candidates])
    inside = chord_to_miles(chords) <= corridor_miles
    found = [
        RouteStation(index.stations[station], float(track.cumulative_miles[vertex]))
        for station, vertex in zip(candidates[inside], nearest[inside], strict=True)
    ]
    return sorted(found, key=lambda item: item.mile_marker)


def find_origin_stations(
    origin: GeoPoint, index: StationIndex, radii_miles: tuple[float, ...]
) -> list[RouteStation]:
    origin_vector = to_unit_vectors([origin.lat], [origin.lng])
    for radius in radii_miles:
        hits = index.within(origin_vector, radius)
        if len(hits):
            return [RouteStation(index.stations[i], 0.0) for i in np.sort(hits)]
    return []


def merge_candidates(
    origin_stations: list[RouteStation], corridor_stations: list[RouteStation]
) -> list[RouteStation]:
    merged = {item.station.opis_id: item for item in corridor_stations}
    merged.update({item.station.opis_id: item for item in origin_stations})
    return sorted(merged.values(), key=lambda item: (item.mile_marker, item.station.opis_id))
