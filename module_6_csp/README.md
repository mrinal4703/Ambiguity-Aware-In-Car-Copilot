# Module 6: CSP and feasibility   (owner: Prasanna)

## What this module does
Decides whether a trip is feasible and, if not, which charging plan makes it feasible. A generic backtracking CSP
solver (forward checking + MRV) is applied to variables station x target charge x route preference with hard
constraints, then solutions are ranked by soft preferences. When nothing is feasible it explains why, per station.

## Inputs and outputs
- Takes in: vehicle state, destination, optional deadline / avoid_tolls / preferred network / excluded stations
  (`ChargingProblem.from_env`), routes from module 5.
- Hands on: `ChargingResult` (best `ChargingSolution` with a `RouteOption`, all solutions,
  per-station `contracts.route.FeasibilityResult`, explanation). `check_direct` checks a trip without charging.

## How to run / test
```bash
python -m pytest module_6_csp
python -c "
from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_6_csp import ChargingPlanner, ChargingProblem
env = CarEnvironment(make_state('low_battery'))
print(ChargingPlanner.from_env(env).solve(ChargingProblem.from_env(env, 'cuttack')).explanation)"
```

## Design notes
- Hard constraints: tools available, connector compatible, station available, not excluded, reach the station with
  the 10 % reserve, charging is useful, reach the destination with the reserve, deadline, no toll.
- Soft score: 0.3 x total time + toll penalty + network preference + energy price + distance from desired 80 %.
- Charge time uses the station power with a DC taper above 80 %.
- Explanations report the constraints blocking the most promising (target, route) combination, e.g. with a 30-minute
  deadline: "cs_kiit: would miss the deadline; cs_airport: connector not compatible with the car; ...".

## Results (low_battery preset, 12 %, Home -> Cuttack)
- Direct trip infeasible; 18 feasible charging plans; best: "Charge at Tata Power EZ Charge, KIIT Square to 80 %
  (28 min), total 55 min, arrive with 67 %".
- With a 30-minute deadline: no plan; each station is explained.

## Known limitations / TODO
- [ ] One charging stop at most.

## Log (newest first)
- 2026-10-28: CSP solver, charging problem, explanations; 14 tests.
