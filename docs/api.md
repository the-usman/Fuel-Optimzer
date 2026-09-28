# API Reference

Base URL for local development: `http://localhost:8000`.

## `GET /api/v1/route/`

Plan a trip and its fuel stops.

| Query param | Required | Description |
|---|---|---|
| `start` | yes | `"City, ST"` (e.g. `Chicago, IL`) or `"lat,lng"` (e.g. `41.8781,-87.6298`). Max 200 chars. |
| `finish` | yes | Same format as `start`. |

Both locations must be inside the contiguous USA (48 states plus DC).

```bash
curl "http://localhost:8000/api/v1/route/?start=Chicago,%20IL&finish=Denver,%20CO"
```

## `POST /api/v1/route/`

Same as GET, with a JSON body. Returns the same result.

```bash
curl -X POST http://localhost:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Denver, CO"}'
```

### 200 response (Chicago, IL to Denver, CO; real output with stops truncated, `elapsed_ms` from a warm process)

```json
{
  "route_id": "790f8631e311",
  "start": {"query": "Chicago, IL", "lat": 41.83705, "lng": -87.68494},
  "finish": {"query": "Denver, CO", "lat": 39.76185, "lng": -104.88111},
  "distance_miles": 1002.7,
  "duration_hours": 17.8,
  "vehicle": {"range_miles": 500.0, "mpg": 10.0, "tank_gallons": 50.0},
  "fuel_stops": [
    {
      "sequence": 1,
      "opis_id": 73127,
      "name": "Gas N Wash",
      "address": "I-55, EXIT 285",
      "city": "Chicago",
      "state": "IL",
      "lat": 41.83705,
      "lng": -87.68494,
      "mile_marker": 0.0,
      "price_per_gallon": "3.399",
      "gallons": "1.28",
      "cost": "4.37"
    }
  ],
  "totals": {"gallons": "100.26", "fuel_cost_usd": "292.02", "stops": 9},
  "map": {
    "html_url": "http://localhost:8000/map/790f8631e311/",
    "geojson": {"type": "FeatureCollection", "features": ["...route LineString, one Point per stop..."]}
  },
  "meta": {"external_api_calls": 1, "cache_hit": false, "elapsed_ms": 174.0}
}
```

Field notes:

- Money and gallons are strings (exact decimals). `totals.fuel_cost_usd` is the sum of the
  stop `cost` values.
- `mile_marker` is the distance along the route where the station sits.
- `map.geojson` holds the simplified route (Douglas-Peucker) plus one `Point` per stop with the
  same properties as `fuel_stops`. The math always runs on the full geometry.
- `meta.external_api_calls` counts HTTP calls made by this request: 1 for a fresh route
  (OSRM only), 0 for a cache hit, up to 3 if both locations needed Nominatim.
- Nine stops for 1,000 miles is intentional: the optimizer buys only what it needs at an
  expensive station and tops up where fuel is cheaper. Fewer stops would cost more.

## `GET /map/<route_id>/`

HTML page (Leaflet + OpenStreetMap tiles) for a planned route, rendered from the cache. It
makes no external API calls. Returns 404 if the id is unknown or its cache entry has expired
(`ROUTE_CACHE_TTL_SECONDS`, 24 h by default).

## `GET /api/v1/health/`

```json
{"status": "ok", "station_count": 6617, "index_loaded": true, "indexed_station_count": 6617}
```

`index_loaded` is false until the first route request builds the in-memory KD-tree.

## Errors

Every error uses one shape:

```json
{"error": {"code": "location_not_found", "message": "Could not find 'Springfeld, IL' in the USA."}}
```

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Missing, blank, or too long parameters. `details` lists the fields. |
| 400 | `invalid_location` | `lat,lng` out of range (e.g. `95,10`). |
| 400 | `location_not_found` | Neither the gazetteer nor Nominatim found the place. |
| 400 | `outside_service_area` | Location outside the contiguous USA (Alaska, Hawaii, abroad). |
| 404 | `not_found` | Unknown route id. |
| 405 | `method_not_allowed` | Unsupported HTTP method. |
| 422 | `no_route_found` | OSRM has no drivable route between the points. |
| 422 | `no_feasible_fuel_plan` | A gap between stations is longer than the vehicle range. `details` has `gap_start_mile` and `gap_end_mile`. |
| 422 | `no_station_near_origin` | Empty tank and no station within `ORIGIN_SEARCH_MILES` of the start. |
| 502 | `routing_provider_error` / `geocoding_provider_error` | Provider failed or returned something invalid. |
| 504 | `routing_provider_timeout` / `geocoding_provider_timeout` | Provider timed out. |
