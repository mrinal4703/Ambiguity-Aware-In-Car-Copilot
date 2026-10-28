# Module 5: Search and route optimisation   (owner: Sistu Neha)

## What this module does
Finds routes on the simulator's road graph with Uniform-Cost Search and A*, under several cost preferences
(fastest, shortest, eco, no_toll, balanced). Provides route alternatives and routes through charging stations, and
plugs into the simulator as its router.

## Inputs and outputs
- Takes in: origin, destination, preference, optional waypoints; the graph built from module 1 (`RoadGraph.from_env`).
- Hands on: `contracts.route.RouteOption` (path, distance_km, time_min, energy_kwh, toll, geometry). Used by module 6
  (charging CSP), module 7 (calculate_route) and module 1 (`make_router`).

## How to run / test
```bash
python -m pytest module_5_search
python -m module_5_search.compare      # A* vs UCS on every node pair
```

## Design notes
- Edge cost = weighted sum of time, distance, energy and a toll penalty (`CostWeights`, `PREFERENCES`).
- A* heuristic: straight-line distance converted with the cheapest possible per-km cost of the preference, which never
  overestimates, so A* stays optimal.
- `RouteSolver.alternatives` returns distinct routes under different preferences; `charging_routes` builds
  origin -> station -> destination legs.

## Results (`python -m module_5_search.compare`, 272 ordered node pairs)
| preference | pairs | same optimal cost as UCS | avg nodes expanded A* | avg expanded UCS |
|---|---|---|---|---|
| fastest | 272 | 1.00 | 6.22 | 8.50 |
| shortest | 272 | 1.00 | 4.45 | 8.50 |
| eco | 272 | 1.00 | 4.58 | 8.50 |
| no_toll | 272 | 1.00 | 5.53 | 7.06 |
| balanced | 272 | 1.00 | 5.70 | 8.50 |

## Changing roads
Closed roads are skipped by the graph and delays raise edge time, so UCS and A* reroute around them with no change to
the algorithms; A* stays equal to UCS (tested on a closed road).

## Known limitations / TODO
- [ ] Delays are per edge and static once set (no time-dependent routing).

## Log (newest first)
- 2026-10-28 (problem-statement review): tests for closed and delayed roads; 13 tests.
- 2026-10-28: graph, UCS, A*, route solver, comparison; 11 tests.
