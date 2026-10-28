"""The simulated car environment (module 1).

`CarEnvironment` owns the mutable state and executes tool calls. Every call
returns a `ToolResult`; nothing else in the system is allowed to claim that an
action happened unless a ToolResult with ok=True says so.

Extra hooks for evaluation (CAR-bench style):
  * `fail_next(tool, error)`       – the next call of `tool` fails
  * `schedule(tool, mutation)`     – mutate the world right before `tool` runs
                                     (e.g. a charging station goes offline)
  * `seed`                         – reproducible random perturbations
                                     (traffic, availability of flaky stations)
"""
from __future__ import annotations

import heapq
import random
from copy import deepcopy
from typing import Any, Callable

from pydantic import BaseModel, Field

from .tool_specs import TOOL_FEATURE, TOOL_SPECS
from .world import default_state, haversine_km

TRAFFIC_FACTOR = {"light": 1.0, "moderate": 1.2, "heavy": 1.6}
HIGHWAY_ENERGY_FACTOR = 1.1
RESERVE_PCT = 10.0  # range shown to the driver keeps this reserve


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: Any = None
    error: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(total_min: float) -> str:
    total = int(round(total_min)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


Router = Callable[["CarEnvironment", str, str, list[str], str], dict[str, Any] | None]


class CarEnvironment:
    def __init__(self, state: dict[str, Any] | None = None, seed: int | None = None,
                 router: Router | None = None, perturb: bool = False):
        self.state = deepcopy(state) if state is not None else default_state()
        self.rng = random.Random(seed)
        self.router = router
        self.log: list[ToolResult] = []
        self._failures: dict[str, list[str]] = {}
        self._scheduled: dict[str, list[Callable[["CarEnvironment"], None]]] = {}
        if perturb:
            self._perturb()

    # ------------------------------------------------------------------ setup
    def _perturb(self) -> None:
        """Small seeded variations so repeated trials are not identical."""
        self.state["driving"]["traffic"] = self.rng.choice(["light", "moderate", "moderate", "heavy"])
        for road in self.state["roads"]:
            road["speed_kmh"] = round(road["speed_kmh"] * self.rng.uniform(0.9, 1.1), 1)

    def fail_next(self, tool: str, error: str = "simulated tool failure") -> None:
        self._failures.setdefault(tool, []).append(error)

    def schedule(self, tool: str, mutation: Callable[["CarEnvironment"], None]) -> None:
        self._scheduled.setdefault(tool, []).append(mutation)

    # -------------------------------------------------------------- accessors
    @property
    def vehicle(self) -> dict[str, Any]:
        return self.state["vehicle"]

    @property
    def driving(self) -> dict[str, Any]:
        return self.state["driving"]

    @property
    def navigation(self) -> dict[str, Any]:
        return self.state["navigation"]

    def battery_kwh(self) -> float:
        v = self.vehicle
        return v["battery_capacity_kwh"] * v["battery_pct"] / 100.0

    def range_km(self, with_reserve: bool = False) -> float:
        v = self.vehicle
        usable_pct = max(0.0, v["battery_pct"] - (RESERVE_PCT if with_reserve else 0.0))
        return v["battery_capacity_kwh"] * usable_pct / 100.0 / v["consumption_kwh_per_km"]

    def station(self, station_id: str) -> dict[str, Any] | None:
        return next((s for s in self.state["stations"] if s["id"] == station_id), None)

    def contact(self, contact_id: str) -> dict[str, Any] | None:
        return next((c for c in self.state["contacts"] if c["id"] == contact_id), None)

    def location_name(self, node: str) -> str:
        loc = self.state["locations"].get(node)
        return loc["name"] if loc else node

    def set_station_availability(self, station_id: str, available: bool) -> None:
        st = self.station(station_id)
        if st is not None:
            st["available"] = available

    def neighbours(self, node: str) -> list[dict[str, Any]]:
        out = []
        for r in self.state["roads"]:
            if r["from"] == node:
                out.append({**r})
            elif r["to"] == node:
                out.append({**r, "from": r["to"], "to": r["from"]})
        return out

    def edge_time_min(self, road: dict[str, Any]) -> float:
        factor = TRAFFIC_FACTOR.get(self.driving["traffic"], 1.0) if road["road_type"] == "city" else 1.0
        return road["distance_km"] / road["speed_kmh"] * 60.0 * factor

    def edge_energy_kwh(self, road: dict[str, Any]) -> float:
        f = HIGHWAY_ENERGY_FACTOR if road["road_type"] == "highway" else 1.0
        return road["distance_km"] * self.vehicle["consumption_kwh_per_km"] * f

    def resolve_node(self, ref: str | None) -> str | None:
        """Accept a location id, a station id or a (partial) location name."""
        if not ref:
            return None
        if ref in self.state["locations"]:
            return ref
        st = self.station(ref)
        if st:
            return st["node"]
        q = ref.lower().strip()
        for node, loc in self.state["locations"].items():
            if q == loc["name"].lower() or q in loc["name"].lower() or q.replace(" ", "_") == node:
                return node
        return None

    # ---------------------------------------------------------------- routing
    def _default_route(self, origin: str, destination: str, waypoints: list[str],
                       preference: str) -> dict[str, Any] | None:
        stops = [origin, *waypoints, destination]
        path: list[str] = [origin]
        dist = time = energy = 0.0
        toll = False
        for a, b in zip(stops, stops[1:]):
            leg = self._dijkstra(a, b, preference)
            if leg is None:
                return None
            p, d, t, e, tl = leg
            path += p[1:]
            dist, time, energy, toll = dist + d, time + t, energy + e, toll or tl
        return self._route_dict(path, dist, time, energy, toll)

    def _dijkstra(self, a: str, b: str, preference: str):
        best = {a: 0.0}
        prev: dict[str, tuple[str, dict]] = {}
        heap = [(0.0, a)]
        while heap:
            c, n = heapq.heappop(heap)
            if n == b:
                break
            if c > best.get(n, float("inf")):
                continue
            for r in self.neighbours(n):
                if preference == "no_toll" and r["toll"]:
                    continue
                w = r["distance_km"] if preference == "shortest" else (
                    self.edge_energy_kwh(r) if preference == "eco" else self.edge_time_min(r))
                nc = c + w
                if nc < best.get(r["to"], float("inf")):
                    best[r["to"]] = nc
                    prev[r["to"]] = (n, r)
                    heapq.heappush(heap, (nc, r["to"]))
        if b not in best:
            return None
        path, roads, n = [b], [], b
        while n != a:
            p, r = prev[n]
            roads.append(r)
            path.append(p)
            n = p
        path.reverse()
        return (path, sum(r["distance_km"] for r in roads), sum(self.edge_time_min(r) for r in roads),
                sum(self.edge_energy_kwh(r) for r in roads), any(r["toll"] for r in roads))

    def _route_dict(self, path, dist, time, energy, toll) -> dict[str, Any]:
        return {"path": path, "distance_km": round(dist, 2), "time_min": round(time, 1),
                "energy_kwh": round(energy, 2), "toll": toll,
                "geometry": {"type": "LineString",
                             "coordinates": [self.state["locations"][n]["coords"] for n in path]}}

    # -------------------------------------------------------------- execution
    def call(self, tool: str, **params: Any) -> ToolResult:
        """Execute one tool call against the simulated world."""
        for mutation in self._scheduled.pop(tool, []):
            mutation(self)
        result = self._dispatch(tool, params)
        self.log.append(result)
        return result

    def _dispatch(self, tool: str, params: dict[str, Any]) -> ToolResult:
        if tool not in TOOL_SPECS:
            return ToolResult(tool=tool, ok=False, params=params, error=f"unknown tool '{tool}'")
        feature = TOOL_FEATURE.get(tool, "")
        if feature and feature not in self.vehicle["features"]:
            return ToolResult(tool=tool, ok=False, params=params, error=f"vehicle has no '{feature}' feature")
        missing = [p for p in TOOL_SPECS[tool].required if params.get(p) in (None, "")]
        if missing:
            return ToolResult(tool=tool, ok=False, params=params, error=f"missing parameters: {missing}")
        if self._failures.get(tool):
            return ToolResult(tool=tool, ok=False, params=params, error=self._failures[tool].pop(0))
        try:
            data = getattr(self, f"_t_{tool}")(**params)
        except ToolError as e:
            return ToolResult(tool=tool, ok=False, params=params, error=str(e))
        except TypeError as e:  # bad parameter names
            return ToolResult(tool=tool, ok=False, params=params, error=f"bad parameters: {e}")
        return ToolResult(tool=tool, ok=True, params=params, data=data)

    # ---- read-only tools
    def _t_get_vehicle_state(self):
        v = deepcopy(self.vehicle)
        v["range_km"] = round(self.range_km(), 1)
        v["range_with_reserve_km"] = round(self.range_km(with_reserve=True), 1)
        return v

    def _t_get_current_location(self):
        n = self.vehicle["location"]
        return {"node": n, "name": self.location_name(n), "coords": self.state["locations"][n]["coords"]}

    def _t_get_driving_context(self):
        return deepcopy(self.driving)

    def _t_get_calendar_events(self, next_only: bool = False):
        now = minutes(self.driving["time"])
        events = sorted((e for e in self.state["calendar"] if minutes(e["start"]) >= now),
                        key=lambda e: minutes(e["start"]))
        events = [{**e, "location_name": self.location_name(e["location"])} for e in events]
        return events[:1] if next_only else events

    def _t_get_contacts(self, query: str | None = None):
        cs = self.state["contacts"]
        if query:
            q = query.lower()
            cs = [c for c in cs if q in c["name"].lower() or q == c["relation"]]
        return deepcopy(cs)

    def _t_search_charging_stations(self, near: str | None = None, radius_km: float = 15.0,
                                    connector: str | None = None):
        node = self.resolve_node(near) or self.vehicle["location"]
        here = self.state["locations"][node]["coords"]
        out = []
        for s in self.state["stations"]:
            d = haversine_km(here, self.state["locations"][s["node"]]["coords"])
            if d <= radius_km and (connector is None or connector in s["connectors"]):
                out.append({**s, "straight_line_km": round(d, 2)})
        return sorted(out, key=lambda s: s["straight_line_km"])

    def _t_get_station_status(self, station_id: str):
        st = self.station(station_id)
        if st is None:
            raise ToolError(f"unknown station '{station_id}'")
        return {"id": st["id"], "available": st["available"]}

    def _t_search_poi(self, category: str, near: str | None = None):
        node = self.resolve_node(near) or self.vehicle["location"]
        here = self.state["locations"][node]["coords"]
        out = [{**p, "straight_line_km": round(haversine_km(here, self.state["locations"][p["node"]]["coords"]), 2)}
               for p in self.state["pois"] if p["category"] == category]
        return sorted(out, key=lambda p: p["straight_line_km"])

    def _t_calculate_route(self, destination: str, origin: str | None = None,
                           waypoints: list[str] | None = None, preference: str = "fastest"):
        o = self.resolve_node(origin) or self.vehicle["location"]
        d = self.resolve_node(destination)
        wps = [self.resolve_node(w) for w in (waypoints or [])]
        if d is None or None in wps:
            raise ToolError(f"unknown location in route request: {destination} / {waypoints}")
        route = (self.router or CarEnvironment._default_route)(self, o, d, wps, preference)
        if route is None:
            raise ToolError("no route found")
        return route

    # ---- state-changing tools
    def _t_set_navigation(self, destination: str, waypoints: list[str] | None = None):
        d = self.resolve_node(destination)
        if d is None:
            raise ToolError(f"unknown destination '{destination}'")
        wps = list(waypoints or [])
        route = self._t_calculate_route(destination=d, waypoints=[self.resolve_node(w) or w for w in wps])
        self.state["navigation"] = {"active": True, "destination": d, "waypoints": wps, "route": route}
        return {"destination": d, "destination_name": self.location_name(d), "waypoints": wps,
                "eta_min": route["time_min"], "distance_km": route["distance_km"], "route": route}

    def _t_add_waypoint(self, waypoint: str):
        nav = self.navigation
        if not nav["active"]:
            raise ToolError("no active navigation to add a waypoint to")
        st = self.station(waypoint)
        if st is not None and not st["available"]:
            raise ToolError(f"charging station '{waypoint}' is currently unavailable")
        if st is None and self.resolve_node(waypoint) is None:
            raise ToolError(f"unknown waypoint '{waypoint}'")
        wps = [*nav["waypoints"], waypoint]
        route = self._t_calculate_route(destination=nav["destination"],
                                        waypoints=[self.resolve_node(w) for w in wps])
        nav.update({"waypoints": wps, "route": route})
        return {"waypoints": wps, "eta_min": route["time_min"], "distance_km": route["distance_km"],
                "route": route}

    def _t_cancel_navigation(self):
        self.state["navigation"] = {"active": False, "destination": None, "waypoints": [], "route": None}
        return {"active": False}

    def _t_send_message(self, contact_id: str, text: str):
        c = self.contact(contact_id)
        if c is None:
            raise ToolError(f"unknown contact '{contact_id}'")
        msg = {"to": contact_id, "name": c["name"], "text": text, "time": self.driving["time"]}
        self.state["messages_sent"].append(msg)
        return msg

    def _t_make_call(self, contact_id: str):
        c = self.contact(contact_id)
        if c is None:
            raise ToolError(f"unknown contact '{contact_id}'")
        call = {"to": contact_id, "name": c["name"], "time": self.driving["time"]}
        self.state["calls"].append(call)
        return call

    def _t_add_reminder(self, text: str, time: str | None = None):
        r = {"text": text, "time": time}
        self.state["reminders"].append(r)
        return r

    def _t_control_ac(self, on: bool | None = None, temperature_c: float | None = None,
                      delta_c: float | None = None):
        ac = self.vehicle["ac"]
        target = ac["temperature_c"]
        if delta_c is not None:
            target = ac["temperature_c"] + float(delta_c)
        if temperature_c is not None:
            target = float(temperature_c)
        if not 16.0 <= target <= 30.0:
            raise ToolError(f"temperature {target} C outside the supported 16-30 C range")
        ac["temperature_c"] = target
        ac["on"] = True if on is None else bool(on)
        return deepcopy(ac)

    def _t_control_windows(self, position: int, window: str = "all"):
        position = int(position)
        if not 0 <= position <= 100:
            raise ToolError("window position must be 0-100")
        ws = self.vehicle["windows"]
        keys = list(ws) if window == "all" else [window]
        for k in keys:
            if k not in ws:
                raise ToolError(f"unknown window '{k}'")
            ws[k] = position
        return deepcopy(ws)

    def _t_play_media(self, query: str | None = None, action: str = "play"):
        self.vehicle["media"] = {"playing": action == "play", "source": query}
        return deepcopy(self.vehicle["media"])

    def _t_play_video(self, title: str | None = None):
        if self.vehicle["speed_kmh"] > 0:
            raise ToolError("video playback is only possible when parked")
        return {"playing_video": title}

    # ------------------------------------------------------------- utilities
    def tool_calls(self, tool: str | None = None, ok: bool | None = None) -> list[ToolResult]:
        return [r for r in self.log if (tool is None or r.tool == tool) and (ok is None or r.ok == ok)]

    def snapshot(self) -> dict[str, Any]:
        """JSON-friendly view for the dashboard."""
        return {"vehicle": self._t_get_vehicle_state(), "driving": deepcopy(self.driving),
                "navigation": deepcopy(self.navigation),
                "messages_sent": deepcopy(self.state["messages_sent"]),
                "calls": deepcopy(self.state["calls"]), "reminders": deepcopy(self.state["reminders"])}


class ToolError(Exception):
    """Raised inside a tool implementation; becomes ToolResult(ok=False)."""
