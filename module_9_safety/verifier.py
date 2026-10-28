"""Outcome verification: never report success unless the world actually changed (module 9)."""
from __future__ import annotations

from typing import Any


def verify_outcome(tool: str, params: dict[str, Any], result: Any, env: Any) -> tuple[bool, str]:
    """`result` is a module-1 ToolResult. Returns (ok, reason)."""
    if result is None or not getattr(result, "ok", False):
        return False, f"{tool} failed: {getattr(result, 'error', 'no result')}"
    st = env.state
    checks = {
        "set_navigation": lambda: env.navigation["active"] and
        env.navigation["destination"] == env.resolve_node(params.get("destination")),
        "add_waypoint": lambda: params.get("waypoint") in env.navigation["waypoints"],
        "cancel_navigation": lambda: not env.navigation["active"],
        "send_message": lambda: bool(st["messages_sent"]) and st["messages_sent"][-1]["to"] == params.get("contact_id"),
        "make_call": lambda: bool(st["calls"]) and st["calls"][-1]["to"] == params.get("contact_id"),
        "add_reminder": lambda: bool(st["reminders"]) and st["reminders"][-1]["text"] == params.get("text"),
        "control_ac": lambda: env.vehicle["ac"]["on"] == (True if params.get("on") is None else bool(params["on"])),
        "control_windows": lambda: all(
            pos == int(params["position"]) for k, pos in env.vehicle["windows"].items()
            if params.get("window", "all") in ("all", k)),
        "play_media": lambda: env.vehicle["media"]["playing"] == (params.get("action", "play") == "play"),
        "get_station_status": lambda: bool(result.data.get("available")),
    }
    fn = checks.get(tool)
    if fn is None:
        return True, "ok"
    ok = bool(fn())
    return ok, "verified" if ok else f"{tool} returned ok but the expected state change is missing"
