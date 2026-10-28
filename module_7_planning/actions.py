"""STRIPS-like action schemas (module 7, owner: Dipanjana).

An action has preconditions (facts that must hold), add effects, delete
effects, a safety class and a recovery strategy. "Tool" actions call the car
simulator; "internal" actions run a computation (CSP, choosing a POI, ...).
Parameter values may reference outputs of earlier steps: "$<action>.<key>".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts import SafetyClass
from module_1_simulator.tool_specs import TOOL_SPECS

INTERNAL_ACTIONS = {"check_range", "choose_charging_station", "choose_poi", "resolve_contact", "compose_answer",
                    "estimate_traffic", "estimate_eta"}
SOFT_TOLL_MAX_SLOWDOWN = 1.30   # soft "avoid tolls": accept a toll-free route up to 30 % slower

# recovery strategies understood by the executor
RETRY = "retry"
REPLAN_EXCLUDE_STATION = "replan_exclude_station"
REPLAN_WITH_CHARGING = "replan_with_charging"
ABORT = "abort"


@dataclass(frozen=True)
class Action:
    name: str
    params: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    pre: frozenset[str] = frozenset()
    add: frozenset[str] = frozenset()
    delete: frozenset[str] = frozenset()
    recovery: str = ABORT
    key: str = ""                      # distinguishes two ground actions with the same name

    @property
    def is_tool(self) -> bool:
        return self.name not in INTERNAL_ACTIONS

    @property
    def safety_class(self) -> SafetyClass:
        spec = TOOL_SPECS.get(self.name)
        return spec.safety_class if spec else SafetyClass.LOW

    def applicable(self, facts: frozenset[str]) -> bool:
        return self.pre <= facts

    def apply(self, facts: frozenset[str]) -> frozenset[str]:
        return (facts - self.delete) | self.add


def A(name: str, pre=(), add=(), delete=(), recovery: str = ABORT, key: str = "", **params: Any) -> Action:
    return Action(name, params, frozenset(pre), frozenset(add), frozenset(delete), recovery, key or name)


def initial_facts(env: Any) -> frozenset[str]:
    f = {"navigating" if env.navigation["active"] else "not_navigating"}
    f.add("moving" if env.vehicle["speed_kmh"] > 0 else "parked")
    return frozenset(f)


def domain_for(goal: str, params: dict[str, Any], env: Any, context: dict[str, Any] | None = None
               ) -> tuple[list[Action], frozenset[str]]:
    """Ground actions relevant for `goal` and the goal facts to reach."""
    ctx = context or {}
    p = {k: v for k, v in params.items() if v is not None}
    nav_dest = env.navigation.get("destination")
    acts: list[Action] = [A("get_vehicle_state", add={"vehicle_known"})]

    if goal == "navigate":
        dest = p.get("destination")
        pref = route_preference(env, dest, p.get("preference", "fastest"), ctx)
        acts += [
            A("check_range", pre={"vehicle_known"}, add={"range_ok"}, recovery=REPLAN_WITH_CHARGING,
              destination=dest),
            A("calculate_route", pre={"range_ok"}, add={"route_calculated"}, destination=dest, preference=pref),
            A("set_navigation", pre={"route_calculated"}, add={"navigating", "at_goal_route"},
              delete={"not_navigating"}, destination=dest),
        ]
        return acts, frozenset({"at_goal_route"})

    if goal in ("find_charging", "navigate_with_charging"):
        dest = p.get("destination") or (nav_dest if goal == "find_charging" else None)
        near = p.get("near")
        near = near if isinstance(near, str) and not near.startswith("@") else None
        anchor = near if ctx.get("charge_near") else None   # hard "near X" only when the driver said so
        acts += [
            A("search_charging_stations", pre={"vehicle_known"}, add={"stations_known"}, near=near, radius_km=40),
            A("choose_charging_station", pre={"stations_known"}, add={"station_chosen"}, recovery=ABORT,
              destination=dest, deadline_min=ctx.get("deadline_min"), avoid_tolls=bool(ctx.get("avoid_tolls")),
              avoid_tolls_strict=bool(ctx.get("avoid_tolls_strict")), near=anchor,
              exclude=tuple(ctx.get("exclude_stations", ()))),
            A("get_station_status", pre={"station_chosen"}, add={"station_available"},
              recovery=REPLAN_EXCLUDE_STATION, station_id="$choose_charging_station.station_id"),
        ]
        if goal == "navigate_with_charging" and dest:
            acts.append(A("set_navigation", pre={"station_available"}, add={"navigating", "charging_stop_set"},
                          delete={"not_navigating"}, recovery=REPLAN_EXCLUDE_STATION, destination=dest,
                          waypoints=["$choose_charging_station.station_id"], key="nav_via_station"))
        else:
            acts += [
                A("add_waypoint", pre={"station_available", "navigating"}, add={"charging_stop_set"},
                  recovery=REPLAN_EXCLUDE_STATION, waypoint="$choose_charging_station.station_id"),
                A("set_navigation", pre={"station_available", "not_navigating"},
                  add={"navigating", "charging_stop_set"}, delete={"not_navigating"},
                  recovery=REPLAN_EXCLUDE_STATION, destination="$choose_charging_station.station_id",
                  key="nav_to_station"),
            ]
        return acts, frozenset({"charging_stop_set"})

    if goal == "find_poi":
        cat = p.get("category", "cafe")
        acts += [
            A("search_poi", add={"pois_known"}, category=cat,
              near=None if p.get("near") in (None, "@current_route") else p.get("near")),
            A("choose_poi", pre={"pois_known"}, add={"poi_chosen"}, category=cat),
            A("add_waypoint", pre={"poi_chosen", "navigating"}, add={"poi_stop_set"},
              waypoint="$choose_poi.node"),
            A("set_navigation", pre={"poi_chosen", "not_navigating"}, add={"navigating", "poi_stop_set"},
              delete={"not_navigating"}, destination="$choose_poi.node", key="nav_to_poi"),
        ]
        return acts, frozenset({"poi_stop_set"})

    if goal in ("send_message", "call_contact"):
        acts.append(A("resolve_contact", add={"contact_resolved"}, recipient=p.get("recipient")))
        if goal == "send_message":
            acts.append(A("send_message", pre={"contact_resolved"}, add={"message_sent"},
                          contact_id="$resolve_contact.contact_id", text=p.get("text", "")))
            return acts, frozenset({"message_sent"})
        acts.append(A("make_call", pre={"contact_resolved"}, add={"call_started"},
                      contact_id="$resolve_contact.contact_id"))
        return acts, frozenset({"call_started"})

    if goal == "info_traffic":
        if "live_traffic" in env.vehicle.get("features", []):
            acts.append(A("get_traffic", add={"traffic_known"}, recovery=RETRY))
        else:   # honest fallback: no live data, estimate from the map and time of day
            acts.append(A("estimate_traffic", add={"traffic_known"}))
        return acts, frozenset({"traffic_known"})

    if goal == "info_eta":
        acts.append(A("estimate_eta", pre={"vehicle_known"}, add={"eta_known"}))
        return acts, frozenset({"eta_known"})

    if goal == "chat":
        acts.append(A("compose_answer", add={"answered"}, text=p.get("text", "")))
        return acts, frozenset({"answered"})

    simple = {
        "climate": ("control_ac", "ac_set", {k: p[k] for k in ("on", "temperature_c", "delta_c") if k in p}),
        "windows": ("control_windows", "windows_set", {k: p[k] for k in ("position", "window") if k in p}),
        "media": ("play_media", "media_set", {k: p[k] for k in ("query", "action") if k in p}),
        "video": ("play_video", "video_playing", {k: p[k] for k in ("title",) if k in p}),
        "reminder": ("add_reminder", "reminder_added", {k: p[k] for k in ("text", "time") if k in p}),
        "info_calendar": ("get_calendar_events", "calendar_known", {"next_only": True}),
        "info_vehicle": ("get_vehicle_state", "vehicle_known", {}),
    }
    if goal in simple:
        tool, fact, tp = simple[goal]
        if tool == "get_vehicle_state":
            return acts, frozenset({fact})
        acts.append(A(tool, add={fact}, recovery=RETRY if tool.startswith("get_") else ABORT, **tp))
        return acts, frozenset({fact})

    raise UnsupportedGoal(goal)


def route_preference(env: Any, dest: Any, pref: str, ctx: dict[str, Any]) -> str:
    """Strict toll avoidance is a hard constraint; the default is soft: take the toll-free
    route only if it is at most SOFT_TOLL_MAX_SLOWDOWN times slower than the requested one."""
    if ctx.get("avoid_tolls_strict"):
        return "no_toll"
    if not ctx.get("avoid_tolls") or not dest:
        return pref
    from module_5_search import RouteSolver   # local import keeps the planner light
    d = env.resolve_node(dest) if hasattr(env, "resolve_node") else dest
    if d is None:
        return pref
    solver = RouteSolver.from_env(env)
    base, free = solver.route(env.vehicle["location"], d, preference=pref), \
        solver.route(env.vehicle["location"], d, preference="no_toll")
    if free is None:
        return pref
    if base is None or free.time_min <= base.time_min * SOFT_TOLL_MAX_SLOWDOWN:
        return "no_toll"
    return pref


class UnsupportedGoal(ValueError):
    pass
