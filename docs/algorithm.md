# Fuel Optimization Algorithm

Implementation: `apps/routing/services/fuel_optimizer.py` (pure function, no Django).

## Assumptions

1. **Vehicle.** Range 500 miles at 10 MPG, so the tank holds 50 gallons. Both come from
   settings (`VEHICLE_RANGE_MILES`, `VEHICLE_MPG`).
2. **Start empty.** The vehicle starts with `STARTING_FUEL_GALLONS` (default 0) and must buy
   fuel at a station at the origin. The reported total therefore covers the whole trip,
   which is what "total money spent on fuel" means. Set the setting to 50 to model "starts
   full".
3. **Arrive empty.** Nothing is bought beyond what is needed to reach the destination.
4. **Detours are free.** Stations are treated as points on the route at their mile marker.
   The short drive from the highway to a station inside the corridor (10 miles by default)
   is not costed.
5. **Station at the origin.** With an empty tank, stations within the corridor radius of the
   start point are snapped to mile 0. If there are none, the search widens around the start
   only (`ORIGIN_SEARCH_MILES`, default 40). If still none, the API returns 422
   `no_station_near_origin`.
6. **Fixed prices** for the duration of the trip.
7. **Station coordinates are city level** (see `decisions.md`), so a mile marker is accurate to
   roughly the size of the town.

## Greedy strategy

Candidate stations are sorted by mile marker. The destination is appended as a final node
with price 0. Starting at the origin station:

1. Look at every node reachable on a full tank (`current mile + range`, inclusive, so a
   station exactly 500 miles ahead is reachable).
2. If a reachable node is **cheaper** than the current station, buy just enough fuel to reach
   the **first** such node, and drive there. Because the destination costs 0, this also covers
   "buy just enough to finish".
3. Otherwise **fill the tank** and drive to the **cheapest** reachable station (ties go to
   the farthest one, which avoids needless stops).
4. If nothing is reachable, raise `NoFeasibleRouteError` with the gap's start and end mile
   (HTTP 422 with `details.gap_start_mile` / `gap_end_mile`).

## Why it is optimal for fixed prices

Every gallon burned between mile `a` and mile `b` must be bought at some station at or before
`a`. Consider the current station `s`:

- If a cheaper station `t` is reachable, any fuel bought at `s` beyond what is needed to reach
  `t` could instead be bought at `t` for less. So buying exactly enough to reach `t` is optimal.
- If no reachable station is cheaper, then every gallon that will be burned within the next
  full tank would otherwise be bought at a station that is at least as expensive. Filling up
  here is optimal, and continuing from the cheapest reachable station preserves the argument
  inductively.

This is the classic exchange argument for the "gas station problem" with a single fixed price
per station (Khuller, Malekian, Mestre, "To fill or not to fill", 2007).

## Complexity

`n` candidate stations, `k` stations within one tank of range:

- Sorting: `O(n log n)`.
- Each step uses `bisect` to find the reach limit and scans at most `k` nodes: `O(n * k)`
  overall, typically a few hundred operations for a cross-country route.

## Money

Prices are `Decimal` from the CSV (up to 8 decimals). Gallons are computed as
`Decimal(miles) / Decimal(mpg)` and kept to a millionth of a gallon so float noise in mile
markers never leaks into money. Stop cost is the exact product `gallons * price`. Rounding to
cents happens only in the presenter, and the trip total is the sum of the rounded stop costs,
so the numbers a client sees always add up.

## Corridor search (feeds the optimizer)

1. OSRM geometry (`[lng, lat]`) is turned into cumulative mile markers with a vectorized
   haversine, then scaled so the last marker equals OSRM's reported distance.
2. Route vertices are sampled every `corridor_miles`. The station KD-tree (3D unit vectors, so
   chord distance is monotonic in great circle distance) returns every station within
   `corridor + step` of any sample. Every vertex is within one step of a sample, so nothing
   inside the corridor is missed.
3. A KD-tree over all route vertices gives each candidate its nearest vertex and distance;
   stations farther than the corridor are dropped, the rest take that vertex's mile marker.
