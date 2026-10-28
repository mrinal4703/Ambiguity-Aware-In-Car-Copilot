"""Route planning on top of UCS / A* (module 5, owner: Sistu Neha).

* `RouteSolver.route`         – best route origin -> [waypoints] -> destination
* `RouteSolver.alternatives`  – k diverse routes (penalty method)
* `RouteSolver.charging_routes` – origin -> station -> destination candidates
* `make_router()`             – plug-in for `CarEnvironment(router=...)`
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from contracts import RouteOption

from .astar import astar
from .graph import CostWeights, Edge, PREFERENCES, RoadGraph
from .uniform_cost import SearchResult, uniform_cost_search


@dataclass
class Leg:
    path: list[str]
    edges: list[Edge]
    cost: float
    expanded: int

    @property
    def distance_km(self) -> float:
        return sum(e.distance_km for e in self.edges)

    @property
    def time_min(self) -> float:
        return sum(e.time_min for e in self.edges)

    @property
    def energy_kwh(self) -> float:
        return sum(e.energy_kwh for e in self.edges)

    @property
    def toll(self) -> bool:
        return any(e.toll for e in self.edges)


@dataclass
class Route:
    path: list[str]
    legs: list[Leg] = field(default_factory=list)

    distance_km = property(lambda self: sum(l.distance_km for l in self.legs))
    time_min = property(lambda self: sum(l.time_min for l in self.legs))
    energy_kwh = property(lambda self: sum(l.energy_kwh for l in self.legs))
    toll = property(lambda self: any(l.toll for l in self.legs))
    cost = property(lambda self: sum(l.cost for l in self.legs))
    expanded = property(lambda self: sum(l.expanded for l in self.legs))

    def as_env_dict(self, coords: dict[str, list[float]]) -> dict[str, Any]:
        return {"path": self.path, "distance_km": round(self.distance_km, 2), "time_min": round(self.time_min, 1),
                "energy_kwh": round(self.energy_kwh, 2), "toll": self.toll,
                "geometry": {"type": "LineString", "coordinates": [coords[n] for n in self.path]},
                "nodes_expanded": self.expanded}


def weights_for(preference: str | CostWeights | None) -> CostWeights:
    if isinstance(preference, CostWeights):
        return preference
    return PREFERENCES.get(preference or "fastest", PREFERENCES["fastest"])


class RouteSolver:
    def __init__(self, graph: RoadGraph, algorithm: str = "astar"):
        if algorithm not in ("astar", "ucs"):
            raise ValueError("algorithm must be 'astar' or 'ucs'")
        self.graph = graph
        self.algorithm = algorithm

    @classmethod
    def from_env(cls, env: Any, algorithm: str = "astar") -> "RouteSolver":
        return cls(RoadGraph.from_env(env), algorithm)

    def _search(self, a: str, b: str, w: CostWeights) -> SearchResult:
        return astar(self.graph, a, b, w) if self.algorithm == "astar" else uniform_cost_search(self.graph, a, b, w)

    def route(self, origin: str, destination: str, waypoints: list[str] | None = None,
              preference: str | CostWeights | None = "fastest") -> Route | None:
        w = weights_for(preference)
        stops = [origin, *(waypoints or []), destination]
        route = Route(path=[origin])
        for a, b in zip(stops, stops[1:]):
            if a == b:
                continue
            r = self._search(a, b, w)
            if not r.found:
                return None
            route.legs.append(Leg(r.path, r.edges, r.cost, r.expanded))
            route.path += r.path[1:]
        return route

    def alternatives(self, origin: str, destination: str, k: int = 3,
                     preference: str | CostWeights | None = "fastest", penalty: float = 1.6) -> list[Route]:
        """Diverse alternatives: after each route, multiply the cost of its edges by `penalty`."""
        base = weights_for(preference)
        used: set[tuple[str, str]] = set()
        out: list[Route] = []
        seen: set[tuple[str, ...]] = set()
        for _ in range(k * 3):
            if len(out) >= k:
                break
            def cost_of(edge_from: str, e: Edge) -> float:
                c = base.edge_cost(e)
                return c * penalty if (edge_from, e.to) in used or (e.to, edge_from) in used else c
            r = _penalised_search(self.graph, origin, destination, cost_of)
            if not r.found:
                break
            key = tuple(r.path)
            for a, b in zip(r.path, r.path[1:]):
                used.add((a, b))
            if key in seen:
                continue
            seen.add(key)
            true_cost = sum(base.edge_cost(e) for e in r.edges)
            out.append(Route(path=r.path, legs=[Leg(r.path, r.edges, true_cost, r.expanded)]))
        return sorted(out, key=lambda r: r.cost)

    def charging_routes(self, origin: str, destination: str | None, stations: list[dict[str, Any]],
                        preference: str | CostWeights | None = "fastest") -> list[RouteOption]:
        """One RouteOption per station: origin -> station node [-> destination]."""
        options = []
        for st in stations:
            node = st["node"]
            leg1 = self.route(origin, node, preference=preference)
            if leg1 is None:
                continue
            leg2 = self.route(node, destination, preference=preference) if destination else None
            if destination and leg2 is None:
                continue
            legs = [leg1] + ([leg2] if leg2 else [])
            options.append(RouteOption(
                id=f"via_{st['id']}",
                waypoints=[st["id"]] + ([destination] if destination else []),
                distance_km=round(sum(l.distance_km for l in legs), 2),
                time_min=round(sum(l.time_min for l in legs), 1),
                energy_kwh=round(sum(l.energy_kwh for l in legs), 2),
                cost=round(sum(l.cost for l in legs), 3),
                metadata={"station_id": st["id"], "station": st, "path": leg1.path + (leg2.path[1:] if leg2 else []),
                          "leg1_km": round(leg1.distance_km, 2), "leg1_kwh": round(leg1.energy_kwh, 2),
                          "leg1_min": round(leg1.time_min, 1),
                          "leg2_km": round(leg2.distance_km, 2) if leg2 else 0.0,
                          "leg2_kwh": round(leg2.energy_kwh, 2) if leg2 else 0.0,
                          "leg2_min": round(leg2.time_min, 1) if leg2 else 0.0,
                          "toll": any(l.toll for l in legs),
                          "nodes_expanded": sum(l.expanded for l in legs)}))
        return sorted(options, key=lambda o: o.cost)

    def direct_option(self, origin: str, destination: str,
                      preference: str | CostWeights | None = "fastest") -> RouteOption | None:
        r = self.route(origin, destination, preference=preference)
        if r is None:
            return None
        return RouteOption(id="direct", waypoints=[destination], distance_km=round(r.distance_km, 2),
                           time_min=round(r.time_min, 1), energy_kwh=round(r.energy_kwh, 2), cost=round(r.cost, 3),
                           metadata={"path": r.path, "toll": r.toll, "leg1_km": round(r.distance_km, 2),
                                     "leg1_kwh": round(r.energy_kwh, 2), "leg1_min": round(r.time_min, 1),
                                     "leg2_km": 0.0, "leg2_kwh": 0.0, "leg2_min": 0.0,
                                     "nodes_expanded": r.expanded})


def _penalised_search(graph: RoadGraph, start: str, goal: str,
                      cost_of: Callable[[str, Edge], float]) -> SearchResult:
    """UCS with an edge-cost callback (used for the alternatives penalty method)."""
    import heapq
    g = {start: 0.0}
    prev: dict[str, tuple[str, Edge]] = {}
    frontier = [(0.0, 0, start)]
    closed: set[str] = set()
    tie = expanded = 0
    while frontier:
        c, _, n = heapq.heappop(frontier)
        if n in closed:
            continue
        if n == goal:
            path, edges, m = [goal], [], goal
            while m != start:
                p, e = prev[m]
                edges.append(e)
                path.append(p)
                m = p
            return SearchResult(path[::-1], c, expanded, edges[::-1])
        closed.add(n)
        expanded += 1
        for e in graph.adj.get(n, []):
            ec = cost_of(n, e)
            if ec == float("inf"):
                continue
            if c + ec < g.get(e.to, float("inf")):
                g[e.to] = c + ec
                prev[e.to] = (n, e)
                tie += 1
                heapq.heappush(frontier, (c + ec, tie, e.to))
    return SearchResult(None, float("inf"), expanded)


def make_router(algorithm: str = "astar"):
    """Return a callable usable as `CarEnvironment(router=make_router())`."""
    def router(env: Any, origin: str, destination: str, waypoints: list[str], preference: str):
        solver = RouteSolver.from_env(env, algorithm)
        r = solver.route(origin, destination, waypoints, preference)
        return None if r is None else r.as_env_dict(solver.graph.coords)
    return router
