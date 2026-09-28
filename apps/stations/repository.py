"""In-memory station catalogue with a KD-tree, loaded once per process.

The request path never queries the database for stations. The first caller loads every
station into immutable domain objects, converts their coordinates to 3D unit vectors
and builds a ``cKDTree`` over them; later callers reuse that index. Loading is guarded by
a lock so concurrent first requests in a threaded server build the index only once.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from scipy.spatial import cKDTree

from apps.routing.domain.entities import Station
from apps.routing.services.route_geometry import FloatArray, miles_to_chord, to_unit_vectors
from apps.stations.models import Station as StationModel

logger = logging.getLogger(__name__)

StationLoader = Callable[[], Sequence[Station]]


@dataclass(frozen=True, slots=True)
class StationIndex:
    stations: tuple[Station, ...]
    unit_vectors: FloatArray
    tree: cKDTree | None

    @classmethod
    def build(cls, stations: Sequence[Station]) -> StationIndex:
        vectors = to_unit_vectors([s.lat for s in stations], [s.lng for s in stations])
        tree = cKDTree(vectors) if stations else None
        return cls(stations=tuple(stations), unit_vectors=vectors.reshape(-1, 3), tree=tree)

    def __len__(self) -> int:
        return len(self.stations)

    def within(self, unit_vectors: FloatArray, radius_miles: float) -> np.ndarray:
        if self.tree is None or len(unit_vectors) == 0:
            return np.empty(0, dtype=np.intp)
        hits = self.tree.query_ball_point(unit_vectors, miles_to_chord(radius_miles))
        flat = [index for group in np.atleast_1d(hits) for index in group]
        return np.unique(np.asarray(flat, dtype=np.intp))


def load_stations_from_database() -> list[Station]:
    rows = StationModel.objects.values_list(
        "opis_id", "name", "address", "city", "state", "latitude", "longitude", "retail_price"
    )
    return [
        Station(opis_id, name, address, city, state, lat, lng, Decimal(price))
        for opis_id, name, address, city, state, lat, lng, price in rows.iterator()
    ]


class StationRepository:
    _instance: StationRepository | None = None
    _instance_lock = threading.Lock()

    def __init__(self, loader: StationLoader = load_stations_from_database) -> None:
        self._loader = loader
        self._index: StationIndex | None = None
        self._lock = threading.Lock()

    @classmethod
    def instance(cls) -> StationRepository:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def is_loaded(self) -> bool:
        return self._index is not None

    def get_index(self) -> StationIndex:
        index = self._index
        if index is not None:
            return index
        with self._lock:
            if self._index is None:
                self._index = self._build_index()
            return self._index

    def reset(self) -> None:
        with self._lock:
            self._index = None

    def _build_index(self) -> StationIndex:
        started = time.perf_counter()
        index = StationIndex.build(self._loader())
        logger.info(
            "stations.index_loaded count=%d elapsed_ms=%.1f",
            len(index),
            (time.perf_counter() - started) * 1000,
        )
        return index
