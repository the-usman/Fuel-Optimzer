"""Offline US place gazetteer built from the public domain Census Bureau "Places" file.

Resolves "City, ST" pairs to coordinates without any network call. Place names are
normalized so that CSV spellings ("Saint Louis", "Fort Worth") match Census spellings
("St. Louis city", "Fort Worth city"): legal suffixes such as city, town, CDP and village
are dropped, accents are removed, common words are folded to one abbreviation and the
final key ignores spaces and punctuation, so "Mc Calla", "O'Donnell" and "La Salle"
match "McCalla", "Odonnell" and "LaSalle".
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path

CONTIGUOUS_US_STATES: frozenset[str] = frozenset(
    "AL AZ AR CA CO CT DE DC FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)

_BALANCE_PATTERN = re.compile(r"\s*\(balance\)\s*$", re.IGNORECASE)
_SUFFIX_PATTERN = re.compile(
    r"\s+(city and borough|city|town|township|village|borough|cdp|municipality|comunidad|"
    r"zona urbana|urbana|corporation|(unified |consolidated |metropolitan |metro )?government)$"
)
_TOKEN_ALIASES: dict[str, str] = {
    "saint": "st",
    "sainte": "ste",
    "fort": "ft",
    "mount": "mt",
    "mountain": "mtn",
}
_ALIAS_SEPARATORS = re.compile(r"[/-]")
_WORD_SPLIT = re.compile(r"[^a-z0-9']+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

Coordinates = tuple[float, float]
StateBounds = tuple[float, float, float, float]
STATE_BOUNDS_PADDING_DEGREES = 0.25


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def strip_legal_suffix(name: str) -> str:
    cleaned = _BALANCE_PATTERN.sub("", name.strip()).lower()
    return _SUFFIX_PATTERN.sub("", cleaned).strip()


def normalize_place_name(name: str) -> str:
    words = _WORD_SPLIT.split(strip_accents(name).lower())
    folded = "".join(_TOKEN_ALIASES.get(word, word) for word in words if word)
    return _NON_ALNUM.sub("", folded)


def place_keys(census_name: str) -> Iterator[str]:
    base = strip_legal_suffix(census_name)
    yield normalize_place_name(base)
    yield normalize_place_name(_BALANCE_PATTERN.sub("", census_name))
    for part in _ALIAS_SEPARATORS.split(base):
        if part.strip():
            yield normalize_place_name(part)


class Gazetteer:
    def __init__(
        self,
        places: dict[tuple[str, str], Coordinates],
        state_bounds: dict[str, StateBounds] | None = None,
    ) -> None:
        self._places = places
        self._state_bounds = state_bounds or {}

    def __len__(self) -> int:
        return len(self._places)

    def lookup(self, city: str, state: str) -> Coordinates | None:
        key = (state.strip().upper(), normalize_place_name(city))
        return self._places.get(key)

    def state_contains(self, state: str, coordinates: Coordinates) -> bool:
        bounds = self._state_bounds.get(state.strip().upper())
        if bounds is None:
            return False
        min_lat, max_lat, min_lng, max_lng = bounds
        lat, lng = coordinates
        pad = STATE_BOUNDS_PADDING_DEGREES
        return min_lat - pad <= lat <= max_lat + pad and min_lng - pad <= lng <= max_lng + pad

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[str, str, float, float]]) -> Gazetteer:
        primary: dict[tuple[str, str], Coordinates] = {}
        aliases: dict[tuple[str, str], Coordinates] = {}
        bounds: dict[str, StateBounds] = {}
        for state, name, lat, lng in rows:
            first, *others = place_keys(name)
            primary.setdefault((state, first), (lat, lng))
            for alias in others:
                aliases.setdefault((state, alias), (lat, lng))
            bounds[state] = _extend_bounds(bounds.get(state), lat, lng)
        return cls({**aliases, **primary}, bounds)

    @classmethod
    def from_file(cls, path: Path) -> Gazetteer:
        return cls.from_rows(_read_census_rows(path))


def _extend_bounds(bounds: StateBounds | None, lat: float, lng: float) -> StateBounds:
    if bounds is None:
        return (lat, lat, lng, lng)
    min_lat, max_lat, min_lng, max_lng = bounds
    return (min(min_lat, lat), max(max_lat, lat), min(min_lng, lng), max(max_lng, lng))


def _read_census_rows(path: Path) -> Iterator[tuple[str, str, float, float]]:
    with path.open(encoding="utf-8-sig") as handle:
        next(handle)
        for line in handle:
            state, name, lat, lng = line.rstrip("\r\n").split("|")
            yield state, name, float(lat), float(lng)


@lru_cache(maxsize=4)
def load_gazetteer(path: Path) -> Gazetteer:
    return Gazetteer.from_file(path)
