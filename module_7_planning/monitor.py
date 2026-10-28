"""Trip monitoring and replanning while driving (module 7, owner: Dipanjana).

The problem statement asks the copilot to revise its plan when conditions change:
a road is closed, the battery drains faster than expected, a charging stop becomes
unavailable, or the driver changes the destination. `TripMonitor.check()` is run
after every turn / drive step and returns the issues it sees; `handle()` repairs
the plan:

    road_closed          -> reroute to the same destination and stops (no new confirmation:
                            the driver already approved them)
    station_unavailable  -> replan the charging stop, excluding that station
    range_risk           -> P(reach destination) under the battery belief is too low and
                            there is no charging stop -> plan navigate_with_charging
    destination_change   -> new destination; check_range adds a charging stop if needed
                            (handled by the normal "navigate" plan and its recovery)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RANGE_P_MIN = 0.80          # replan when P(reach with reserve) drops below this
RESERVE_PCT = 10.0


@dataclass
class TripIssue:
    kind: str                       # road_closed | station_unavailable | range_risk
    detail: str
    goal: str | None = None         # goal to replan with (None = reroute only)
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


class TripMonitor:
    def __init__(self, env: Any, belief: Any | None = None, range_p_min: float = RANGE_P_MIN):
        self.env = env
        self.belief = belief          # module 3 WorldBelief (duck-typed: p_reach, cautious_consumption)
        self.range_p_min = range_p_min
        self.target_station: str | None = None   # set when the trip's destination is a charging station

    # ----------------------------------------------------------------- detect
    def p_reach(self) -> float | None:
        nav = self.env.navigation
        if not nav.get("active") or not nav.get("route"):
            return None
        energy = float(nav["route"]["energy_kwh"])
        if self.belief is not None:
            return float(self.belief.p_reach(energy, RESERVE_PCT))
        v = self.env.vehicle
        usable = v["battery_capacity_kwh"] * max(0.0, v["battery_pct"] - RESERVE_PCT) / 100.0
        return 1.0 if energy <= usable else 0.0

    def check(self) -> list[TripIssue]:
        env, nav = self.env, self.env.navigation
        if not nav.get("active"):
            return []
        issues: list[TripIssue] = []
        blocked = env.route_blocked()
        if blocked:
            a, b = blocked[0]
            issues.append(TripIssue("road_closed", f"the road {env.location_name(a)} - {env.location_name(b)} "
                                                    f"is closed"))
        stops = [env.station(w) for w in nav.get("waypoints", [])]
        stations = [s for s in stops if s is not None]
        for st in stations:
            if not st["available"]:
                issues.append(TripIssue("station_unavailable", f"{st['name']} is no longer available",
                                        "navigate_with_charging", {"destination": nav["destination"]},
                                        {"exclude_stations": (st["id"],)}))
        tgt = self.env.station(self.target_station) if self.target_station else None
        if tgt is not None and tgt["node"] == nav["destination"] and not tgt["available"]:
            issues.append(TripIssue("station_unavailable", f"{tgt['name']} is no longer available",
                                    "find_charging", {}, {"exclude_stations": (tgt["id"],),
                                                          "replace_destination": True}))
            stations = stations + [tgt]
        if not stations:
            p = self.p_reach()
            if p is not None and p < self.range_p_min:
                issues.append(TripIssue("range_risk", f"the battery is draining faster than expected; "
                                                      f"chance of arriving with the reserve is {p:.0%}",
                                        "navigate_with_charging", {"destination": nav["destination"]}))
        return issues

    # ----------------------------------------------------------------- repair
    def reroute(self) -> dict[str, Any]:
        nav = self.env.navigation
        res = self.env.call("set_navigation", destination=nav["destination"], waypoints=list(nav["waypoints"]))
        return {"ok": res.ok, "error": res.error, "route": res.data["route"] if res.ok else None}

    def handle(self, issue: TripIssue, executor: Any, context: dict[str, Any] | None = None):
        """Returns the reroute result (road_closed) or the executor report of the new plan."""
        if issue.goal is None:
            return self.reroute()
        ctx = {**(context or {}), **issue.context}
        if ctx.pop("replace_destination", False):   # the trip's goal itself is gone: plan a new one
            self.env.call("cancel_navigation")
        if self.belief is not None:
            ctx.setdefault("consumption_factor", self.belief.cautious_consumption())
            ctx.setdefault("station_availability", self.belief.availability())
        return executor.start(issue.goal, issue.params, ctx)
