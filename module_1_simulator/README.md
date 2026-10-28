# Module 1: Simulator and environment   (owner: Ramesh)

## What this module does
A deterministic, synthetic in-car world around Bhubaneswar that every other module runs against: a 17-node road
network, 8 charging stations, POIs, a calendar, contacts and a vehicle. All tools in the PDF are implemented as
Python calls on `CarEnvironment`, each returning a `ToolResult` and appended to `env.log`.

## Inputs and outputs
- Takes in: tool calls `env.call(tool, **params)` (names in `tool_specs.TOOL_SPECS`).
- Hands on: `contracts.tools.ToolResult`, `env.snapshot()` (vehicle, driving, navigation, messages, calls, reminders),
  `ToolSpec`s with a safety class (low / consequential / high).

## How to run / test
```bash
python -m pytest module_1_simulator
python -c "from module_1_simulator.environment import CarEnvironment; e=CarEnvironment(); print(e.call('get_vehicle_state'))"
```

## Design notes
- Tools: get_vehicle_state, get_current_location, get_driving_context, get_calendar_events, get_contacts,
  search_charging_stations, get_station_status, search_poi, calculate_route, set_navigation, add_waypoint,
  cancel_navigation, send_message, make_call, add_reminder, control_ac, control_windows, play_media, play_video.
- Road distance = haversine x `ROAD_FACTOR` 1.25; energy from the car's kWh/km; a 10 % battery reserve is used by
  every feasibility check.
- Presets in `initial_states.py`: default (35 %), low_battery (12 %), critical_battery (3 %), highway, parked,
  storm, cool_cabin, no_windows_feature.
- Traps for the other modules: two contacts called Rahul, a landlord who does not accept messages, a CHAdeMO-only
  station (car is CCS2), an unavailable station, a slow Type2 charger.
- Dynamic events: `env.schedule(...)` / `env.fail_next(tool)` make a station go offline or a tool time out mid-plan;
  `perturb=True` with a seed varies traffic and speeds for repeated trials (Pass^3).
- Swappable router: module 5 plugs in its A* via `router=`.

## Known limitations / TODO
- [ ] Synthetic coordinates and road speeds; no live traffic or map data.
- [ ] Charging is modelled as a single stop duration, not a time-stepped simulation.

## Log (newest first)
- 2026-10-28: world, environment, tool specs, presets, dynamic events; 15 tests.
