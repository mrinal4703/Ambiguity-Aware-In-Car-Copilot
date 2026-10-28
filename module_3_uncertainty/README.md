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

## Known limitations / TODO
- [ ] Context weights are hand-set, not learned.
- [ ] Temperature is fitted on a small synthetic set.

## Log (newest first)
- 2026-10-28: belief builder, calibration, context resolver; 12 tests.
