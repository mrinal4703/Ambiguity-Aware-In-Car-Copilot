"""Capability checks (module 9, owner: Nishkarsh).

Answers "can this car do this at all?" from the tool registry and the vehicle's
feature list, independently of the LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module_1_simulator.tool_specs import TOOL_FEATURE, TOOL_SPECS, UNSUPPORTED_FEATURES

GOAL_TOOLS = {
    "navigate": ["calculate_route", "set_navigation"],
    "navigate_with_charging": ["search_charging_stations", "set_navigation"],
    "find_charging": ["search_charging_stations", "get_station_status"],
    "find_poi": ["search_poi"],
    "send_message": ["send_message"],
    "call_contact": ["make_call"],
    "climate": ["control_ac"],
    "windows": ["control_windows"],
    "media": ["play_media"],
    "video": ["play_video"],
    "reminder": ["add_reminder"],
    "info_calendar": ["get_calendar_events"],
    "info_vehicle": ["get_vehicle_state"],
    "info_eta": ["get_vehicle_state"],
    "info_traffic": [],          # live traffic is optional: without it the copilot estimates from the map
    "chat": [],
}

ALTERNATIVES = {
    "seat_massage": "I can adjust the AC or find a rest stop instead.",
    "seat_heating": "I can raise the cabin temperature instead.",
    "heated_steering": "I can raise the cabin temperature instead.",
    "sunroof": "I can open the windows instead (when it is safe).",
    "autopilot": "I can't drive the car, but I can navigate and find a rest stop.",
    "windows": "I can adjust the AC instead.",
    "video": "I can play music or a podcast instead.",
    "climate": "I can open the windows a little instead.",
    "live_traffic": "I can estimate the travel time from the map instead.",
    "parking_assist": "I can find a parking spot near your destination instead.",
    "lane_assist": "I can't steer the car; please keep both hands on the wheel. I can find a rest stop if you are tired.",
}


@dataclass
class CapabilityResult:
    supported: bool
    reason: str = ""
    alternative: str = ""
    missing_feature: str | None = None


def tool_supported(tool: str, env: Any) -> CapabilityResult:
    if tool not in TOOL_SPECS:
        return CapabilityResult(False, f"there is no tool called '{tool}'")
    feat = TOOL_FEATURE.get(tool, "")
    if feat and feat not in env.vehicle["features"]:
        return CapabilityResult(False, f"this car has no {feat.replace('_', ' ')} feature",
                                ALTERNATIVES.get(feat, ""), feat)
    return CapabilityResult(True)


def check_request(goal: str, params: dict[str, Any], env: Any) -> CapabilityResult:
    """Is the requested goal something the car can do?"""
    if goal == "unsupported":
        f = params.get("feature", "unknown")
        name = UNSUPPORTED_FEATURES.get(f, str(f).replace("_", " "))
        return CapabilityResult(False, f"this car does not support {name}", ALTERNATIVES.get(f, ""), f)
    tools = GOAL_TOOLS.get(goal)
    if tools is None:
        return CapabilityResult(False, f"I don't know how to '{goal}'")
    for t in tools:
        r = tool_supported(t, env)
        if not r.supported:
            return r
    return CapabilityResult(True)
