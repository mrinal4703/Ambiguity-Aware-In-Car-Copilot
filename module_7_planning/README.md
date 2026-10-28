# Module 7: Sequential planning   (owner: Dipanjana)

## What this module does
Turns a goal into an ordered plan of tool calls with STRIPS-style preconditions and effects, executes it step by step
through the safety gate, verifies each result, and replans when the world changes (station goes offline, range
check fails, tool times out).

## Inputs and outputs
- Takes in: goal + parameters (from the chosen candidate), the environment (module 1), a safety gate (module 9).
- Hands on: `contracts.plan.Plan` (steps with depends_on and recovery) and an `ExecutionReport` (outcomes, replans,
  blackboard, status completed / paused_for_confirmation / blocked / failed).

## How to run / test
```bash
python -m pytest module_7_planning
```

## Design notes
- Action schemas in `actions.py`; goals include navigate, navigate_with_charging, send_message, make_call,
  set_temperature, find_poi, add_reminder, open_windows, ...
- Planner: breadth-first forward search over symbolic facts (shortest valid plan), then dependency links.
- Internal actions (check_range, choose_charging_station via module 6, choose_poi, resolve_contact) write to a
  blackboard; later steps reference values like `$choose_poi.node`.
- Recovery per step: retry (timeouts), replan_exclude_station (station unavailable), replan_with_charging
  (not enough range), abort.
- Execution pauses when the gate asks for confirmation and resumes after the driver answers.

## Known limitations / TODO
- [ ] BFS is fine for these short plans; a heuristic planner would be needed for long ones.

## Log (newest first)
- 2026-10-28: action schemas, planner, executor with verification and replanning; 13 tests.
