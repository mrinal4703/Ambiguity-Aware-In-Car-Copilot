"""Tool schemas exposed by the simulator (module 1).

Each tool has a `ToolSpec` (shared contract) plus the vehicle feature it needs.
Module 9 (safety) and module 7 (planning) read these; module 2 (NLU) uses the
names as its action vocabulary.
"""
from __future__ import annotations

from contracts import SafetyClass, ToolSpec

L, C, X = SafetyClass.LOW, SafetyClass.CONSEQUENTIAL, SafetyClass.CRITICAL

TOOL_SPECS: dict[str, ToolSpec] = {s.name: s for s in [
    # ---- read-only context tools (proactive use is fine) ----
    ToolSpec(name="get_vehicle_state", description="Battery, range, speed, gear, climate, windows, location."),
    ToolSpec(name="get_current_location", description="Current node id, name and coordinates."),
    ToolSpec(name="get_driving_context", description="Road type, traffic, weather, difficulty, time."),
    ToolSpec(name="get_calendar_events", description="Upcoming calendar events.",
             parameters={"next_only": "bool"}),
    ToolSpec(name="get_contacts", description="Contacts, optionally filtered by a name query.",
             parameters={"query": "str"}),
    ToolSpec(name="search_charging_stations", description="Charging stations near a location.",
             parameters={"near": "location id", "radius_km": "float", "connector": "str"},
             preconditions=["location_known"]),
    ToolSpec(name="get_station_status", description="Live availability of one station.",
             parameters={"station_id": "str"}, required=["station_id"]),
    ToolSpec(name="search_poi", description="Points of interest by category near a location.",
             parameters={"category": "cafe|rest_area|pharmacy|hospital", "near": "location id"},
             required=["category"]),
    ToolSpec(name="calculate_route", description="Route between two locations, optional waypoints.",
             parameters={"origin": "location id", "destination": "location id",
                         "waypoints": "list[location id]", "preference": "fastest|shortest|eco|no_toll"},
             required=["destination"], preconditions=["destination_known"]),
    # ---- state-changing tools ----
    ToolSpec(name="set_navigation", description="Replace the active navigation destination.",
             parameters={"destination": "location id", "waypoints": "list[location id]"},
             required=["destination"], preconditions=["destination_known"], safety_class=C),
    ToolSpec(name="add_waypoint", description="Insert a stop (location or charging station) into the route.",
             parameters={"waypoint": "location id or station id"}, required=["waypoint"],
             preconditions=["navigation_active"], safety_class=C),
    ToolSpec(name="cancel_navigation", description="Stop navigation.", safety_class=C),
    ToolSpec(name="send_message", description="Send a text message to a contact.",
             parameters={"contact_id": "str", "text": "str"}, required=["contact_id", "text"],
             preconditions=["recipient_known"], safety_class=C, requires_confirmation=True),
    ToolSpec(name="make_call", description="Call a contact.", parameters={"contact_id": "str"},
             required=["contact_id"], preconditions=["recipient_known"], safety_class=C,
             requires_confirmation=True),
    ToolSpec(name="add_reminder", description="Create a reminder.",
             parameters={"text": "str", "time": "HH:MM"}, required=["text"]),
    ToolSpec(name="control_ac", description="Turn AC on/off and set temperature (16-30 C).",
             parameters={"on": "bool", "temperature_c": "float", "delta_c": "float"}),
    ToolSpec(name="control_windows", description="Set window opening 0-100 percent.",
             parameters={"position": "int 0-100", "window": "all|front_left|front_right|rear_left|rear_right"},
             required=["position"], safety_class=X),
    ToolSpec(name="play_media", description="Play or pause audio.",
             parameters={"query": "str", "action": "play|pause"}),
    ToolSpec(name="play_video", description="Play video on the centre screen (only when parked).",
             parameters={"title": "str"}, safety_class=X),
]}

# Which vehicle feature each tool needs (checked against vehicle.features).
TOOL_FEATURE: dict[str, str] = {
    "get_vehicle_state": "", "get_current_location": "", "get_driving_context": "",
    "get_calendar_events": "calendar", "get_contacts": "calls",
    "search_charging_stations": "charging_search", "get_station_status": "charging_search",
    "search_poi": "poi_search", "calculate_route": "navigation", "set_navigation": "navigation",
    "add_waypoint": "navigation", "cancel_navigation": "navigation", "send_message": "messaging",
    "make_call": "calls", "add_reminder": "reminders", "control_ac": "climate",
    "control_windows": "windows", "play_media": "media", "play_video": "video",
}

# Things drivers ask for that the simulated car does NOT have (for capability tests).
UNSUPPORTED_FEATURES: dict[str, str] = {
    "seat_massage": "seat massage", "sunroof": "sunroof control", "autopilot": "self-driving / autopilot",
    "heated_steering": "heated steering wheel", "seat_heating": "seat heating",
}
