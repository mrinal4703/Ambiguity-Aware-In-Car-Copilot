# Module 3: Uncertainty estimation   (owner: Swastika)

## What this module does
Builds a belief over what the driver means: NLU candidates are re-weighted with the car's context, calibrated into
probabilities, and references are resolved with read-only tool lookups (calendar, contacts, location) before anyone
asks the driver. It separates "what does the user mean" from "can the system do it".

## Inputs and outputs
- Takes in: `Task` from module 2, vehicle and driving context, a tool caller (module 1).
- Hands on: `BeliefBundle` -> `contracts.belief.BeliefState` (candidates with probabilities, differing
  parameters, entropy) plus an `UncertaintyReport` and the parameters that can be resolved internally.

## How to run / test
```bash
python -m pytest module_3_uncertainty
```

## Design notes
- Context weights: e.g. "I need tea" while driving favours finding a cafe over a reminder; "I'm hot" favours AC when
  the cabin is warm.
- Calibration: temperature scaling p_i ∝ score_i^(1/T), T fitted by NLL; ECE reported (`calibration.py`).
- `ContextResolver`: "my next meeting" -> calendar event + location; "my manager" -> contact relation;
  "message Rahul that I'll be late" -> the Rahul who attends the next meeting; possessives ("my landlord") stripped.
  Every lookup is logged so the dashboard can show it.

## Beliefs about the world (problem-statement review)
`world_beliefs.py` keeps probabilistic beliefs, updated from observations while driving:
- `StationBelief`: Beta over "station is free on arrival" (status reports, failures).
- `BatteryBelief`: normal belief over real / model consumption; `p_reach` = P(arrive with the reserve);
  a cautious 90 % quantile is passed to module 6 so plans tighten when the battery drains faster than expected.
- `TravelTimeBelief` / `RoadBelief`: log-normal travel time per road and P(road congested), from traffic reports.
- `WorldBelief` bundles them; `summary()` feeds the dashboard and the ETA (mean and 90 % arrival time).

`preferences.py` learns from the driver's past choices: a Dirichlet per request type ("tea", "tired", ...) with the
parser's prior as pseudo-counts, p(o | choices) = (a0 prior_o + n_o) / (a0 + N), a0 = 0.5. One odd choice does not
flip the behaviour; two consistent ones let the copilot act without asking.

`ContextResolver.next_events()` finds overlapping appointments; "my next appointment" then has two candidate
destinations and the EVPI step asks which one.

## Known limitations / TODO
- [ ] Context weights are hand-set; only the choice preferences are learned.
- [ ] Temperature is fitted on a small synthetic set.

## Log (newest first)
- 2026-10-28 (problem-statement review): world beliefs (stations, battery, travel time, roads), preference learning, conflicting calendar; 17 tests.
- 2026-10-28: belief builder, calibration, context resolver; 12 tests.
