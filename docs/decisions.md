# Decisions and Trade-offs

## Routing: OSRM public server

- Free, no API key, returns the full geometry and distance in one call, and is fast.
- The demo server has no SLA and is rate limited. `OSRM_BASE_URL` and `OSRM_PROFILE` are
  settings, so a self-hosted OSRM can be used without code changes. OpenRouteService would need
  a key and a different response parser.
- Exactly one routing call per uncached trip. Retries apply to connection errors only, so a
  slow provider never produces extra calls.

## Geocoding: offline Census gazetteer first, Nominatim last

- User input and CSV rows are resolved against the public domain US Census Bureau 2025
  Gazetteer "Places" file, trimmed to 4 columns (`data/us_places_gazetteer.txt`, 1.2 MB,
  32,350 places). No network, no rate limit, deterministic.
- Name normalization strips legal suffixes (city, town, CDP, village, "(balance)", ...),
  removes accents, folds Saint/St, Fort/Ft, Mount/Mt, and compares alphanumerics only, so
  "Mc Calla", "O'Donnell", "La Salle" and "Saint Louis" all match.
- The gazetteer matched 3,584 of the 3,809 unique US (city, state) pairs. The other 225 are
  mostly New England townships and unincorporated communities that are not Census "places".
  They were resolved once through Nominatim (structured `city` + `state` query, 1 request per
  second) and committed to `data/geocode_cache.json`. A result is rejected if it falls
  outside the requested state's bounding box, which caught Nominatim returning Canton, MS for
  "Canton, MI".
- At request time Nominatim is only a fallback for free-text input, and its answers are
  cached, so a normal request makes 1 external call and the worst case makes 3.

## City level station coordinates

The CSV addresses are highway exit descriptions ("I-44, EXIT 283 & US-69"), which cannot be
geocoded reliably. Each station takes its city's coordinates. This is acceptable here because:

- Truck stops sit on the highway through or next to the town they are named after, usually
  within a few miles of the city point.
- The corridor is 10 miles wide on each side, so city level error rarely moves a station in
  or out of the corridor, and it shifts mile markers by a few miles at most, which is small
  compared with a 500 mile tank.
- The alternative (geocoding 6,600 exit descriptions) would need a paid or rate limited
  service and still be unreliable.

Consequence: several stations in the same city share a point. The optimizer still picks the
cheapest one.

## Import results (real CSV)

| Metric | Value |
|---|---|
| Rows read | 8,151 |
| Canadian rows dropped | 620 |
| Duplicate OPIS rows merged (lowest price kept, longest name kept) | 905 |
| Unique US stations | 6,626 |
| Stations imported | 6,617 |
| Stations skipped (place could not be geocoded) | 9 |

The import is idempotent: it clears and bulk inserts inside one transaction.

## Empty vs full starting tank

Default is **empty**: the first purchase happens at a station at the origin and the total
reflects the cost of the whole trip, which is what the assignment asks for. `STARTING_FUEL_GALLONS`
switches to "starts full" (or anything in between); the origin station search is then skipped.

## Caching

- Key: SHA-256 of the start and finish coordinates rounded to 4 decimals (about 11 m). The
  first 12 hex characters are the public `route_id`, so the same trip always has the same id.
- Value: the full rendered payload. The map page reads it directly; it never calls OSRM.
- Backend: a file-based cache in `.cache/` by default, so saved routes and map links survive a
  server restart (the in-memory cache lost them). Set `REDIS_URL` to use Django's built-in Redis backend
  (requires installing the `redis` package), which also shares map pages across workers.
- TTL: `ROUTE_CACHE_TTL_SECONDS` (24 h). Fuel prices are static in this exercise.

## Performance

- Stations and their KD-tree load once per process (about 35 ms for 6,617 stations).
- Douglas-Peucker first thins the polyline by travelled length (vectorized), then splits.
  This cut simplification of a 41,000 vertex route from 146 ms to about 10 ms.
- The response geometry is simplified (tolerance 0.005 degrees, about 500 m) to keep the
  payload small (Chicago to Denver: 9,208 OSRM vertices become 148); all math uses the
  full geometry.

## Benchmark

`python scripts/benchmark.py`, live OSRM, run 2026-09-28 on a Windows 11 laptop,
Python 3.14, 6,617 stations. "server ms" is total time minus the OSRM round trip.

| Route | Miles | Stops | Fuel cost | Total ms | OSRM ms | Server ms | Calls | Cache hit ms | Hit calls |
|---|---|---|---|---|---|---|---|---|---|
| New York, NY to Los Angeles, CA | 2810.4 | 18 | $852.60 | 1180 | 1148 | 32.1 | 1 | 0.25 | 0 |
| Chicago, IL to Denver, CO | 1002.7 | 9 | $292.02 | 174 | 165 | 8.5 | 1 | 0.15 | 0 |
| Seattle, WA to Miami, FL | 3303.0 | 20 | $1026.91 | 389 | 357 | 32.1 | 1 | 0.26 | 0 |
| Dallas, TX to Atlanta, GA | 778.8 | 5 | $217.36 | 193 | 171 | 21.6 | 1 | 0.24 | 0 |
| Boston, MA to San Francisco, CA | 3140.4 | 22 | $976.54 | 357 | 272 | 84.9 | 1 | 0.47 | 0 |

Averages: server time excluding OSRM **35.9 ms** (target under 150 ms), cache hit
**0.28 ms** (target under 20 ms), **1.0** external call per cache miss, **0** per hit.
Times are measured in process (no HTTP overhead); OSRM latency varies from run to run.

The first request after a process starts also loads the gazetteer and the station index
(a few hundred ms in total). Later requests reuse both.

## Dependencies

Only the packages listed in the brief are used. `urllib3` is pinned in `requirements.txt`
because `http_session.py` imports its `Retry` class directly (it is already a dependency of
`requests`).
