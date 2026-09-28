# Fuel Route Optimizer API

A Django REST API that takes a start and a finish anywhere in the contiguous USA, and returns
the driving route, the cheapest places to refuel along it (500 mile range, 10 MPG), the total
fuel cost, and a map. Stations and prices come from the provided OPIS CSV, geocoded offline
against the US Census gazetteer. Each new trip makes **one** external call (OSRM). Server
time excluding that call averages about **36 ms**, and repeated trips are served from the
cache in **under 1 ms**.

## Features

- `GET` or `POST /api/v1/route/` with `"City, ST"` or `"lat,lng"` locations.
- Cost optimal fuel plan (greedy "gas station problem" algorithm), exact `Decimal` money.
- Map as GeoJSON in the response and as a Leaflet page at `/map/<route_id>/`.
- `meta.external_api_calls`, `cache_hit` and `elapsed_ms` in every response.
- One consistent error shape with clear codes (400, 404, 422, 502, 504).
- Health endpoint with station and index status.
- Idempotent CSV import with deduplication, Canada filtering and offline geocoding.
- 91 tests, 99 percent coverage (100 percent on the optimizer), no real network in tests.

## Quick start

```bash
git clone <repo-url> fuel-route-optimizer && cd fuel-route-optimizer
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # optional, defaults work for local use
python manage.py migrate
python manage.py import_stations data/fuel-prices-for-be-assessment.csv
python manage.py runserver
```

The import uses the committed gazetteer and geocode cache, so it needs no network
(add `--offline` to guarantee that). With `make`: `make install migrate import run`.

Python 3.12+ is required (Django 6.1.1). Developed and tested on Python 3.14.

## Example

```bash
curl "http://localhost:8000/api/v1/route/?start=Chicago,%20IL&finish=Denver,%20CO"
```

```json
{
  "route_id": "790f8631e311",
  "start": {"query": "Chicago, IL", "lat": 41.83705, "lng": -87.68494},
  "finish": {"query": "Denver, CO", "lat": 39.76185, "lng": -104.88111},
  "distance_miles": 1002.7,
  "duration_hours": 17.8,
  "vehicle": {"range_miles": 500.0, "mpg": 10.0, "tank_gallons": 50.0},
  "fuel_stops": [
    {"sequence": 1, "opis_id": 73127, "name": "Gas N Wash", "address": "I-55, EXIT 285",
     "city": "Chicago", "state": "IL", "lat": 41.83705, "lng": -87.68494, "mile_marker": 0.0,
     "price_per_gallon": "3.399", "gallons": "1.28", "cost": "4.37"}
  ],
  "totals": {"gallons": "100.26", "fuel_cost_usd": "292.02", "stops": 9},
  "map": {"html_url": "http://localhost:8000/map/790f8631e311/", "geojson": {"type": "FeatureCollection", "features": []}},
  "meta": {"external_api_calls": 1, "cache_hit": false, "elapsed_ms": 174.0}
}
```

Open `map.html_url` in a browser to see the route and stops. Full reference: [docs/api.md](docs/api.md).

## Tests and lint

```bash
make test        # pytest
make coverage    # pytest --cov=apps --cov-report=term-missing
make lint        # ruff check . && ruff format --check .
make bench       # 5 real routes against live OSRM
```

## Documentation

- [docs/architecture.md](docs/architecture.md): layers, request flow (Mermaid), why each piece exists.
- [docs/algorithm.md](docs/algorithm.md): the greedy strategy, why it is optimal, assumptions, complexity.
- [docs/api.md](docs/api.md): endpoints, parameters, examples, error codes.
- [docs/decisions.md](docs/decisions.md): trade-offs, import results, benchmark results.
- [docs/postman_collection.json](docs/postman_collection.json): 5 demo routes, error cases, health check.

## Design highlights

- **One routing call.** Locations resolve locally (coordinates or the Census gazetteer);
  only OSRM is called. Nominatim is a cached fallback for free-text input only.
- **In-memory KD-tree.** Stations load once per process into a `cKDTree` over 3D unit
  vectors; a two-stage corridor search finds stations near the route and their mile markers.
- **Pure optimizer.** `fuel_optimizer.py` has no Django imports, uses `Decimal` for money,
  and is covered 100 percent by unit tests.
- **Caching.** Trips are cached by rounded coordinates under a deterministic `route_id`; the
  map page renders from the cache and never calls OSRM.
- **Thin views, injected services.** Views validate and delegate to `TripPlanner`, which gets
  its geocoder, router, repository and cache from one composition root.

Station coordinates are city level approximations (the CSV only has highway exit
descriptions); see [docs/decisions.md](docs/decisions.md) for why that is acceptable here.
