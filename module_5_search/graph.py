"""Weighted road graph G = (V, E) built from the simulator (module 5).

Each edge carries distance (km), travel time (min, traffic-adjusted), energy
(kWh) and a toll flag. Costs are combined by `CostWeights`:

    cost(e) = w_T * T(e) + w_D * D(e) + w_E * E(e) + w_C * C(e)

where C(e) is a preference cost (here: toll penalty).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module_1_simulator.world import haversine_km


@dataclass(frozen=True)
class Edge:
    to: str
    distance_km: float
    time_min: float
    energy_kwh: float
    toll: bool
    road_type: str


@dataclass(frozen=True)
class CostWeights:
    time: float = 1.0
    distance: float = 0.0
    energy: float = 0.0
    toll: float = 0.0            # added once per toll edge; float("inf") forbids tolls

    def edge_cost(self, e: Edge) -> float:
        c = self.time * e.time_min + self.distance * e.distance_km + self.energy * e.energy_kwh
        if e.toll and self.toll:
            c += self.toll
        return c


PREFERENCES: dict[str, CostWeights] = {
    "fastest": CostWeights(time=1.0),
    "shortest": CostWeights(time=0.0, distance=1.0),
    "eco": CostWeights(time=0.0, energy=1.0),
    "no_toll": CostWeights(time=1.0, toll=float("inf")),
    "balanced": CostWeights(time=1.0, distance=0.5, energy=2.0, toll=5.0),
}


class RoadGraph:
    def __init__(self, coords: dict[str, list[float]], adjacency: dict[str, list[Edge]],
                 max_speed_kmh: float, min_kwh_per_km: float, road_factor_min: float = 1.0):
        self.coords = coords
        self.adj = adjacency
        self.max_speed_kmh = max_speed_kmh
        self.min_kwh_per_km = min_kwh_per_km
        self.road_factor_min = road_factor_min

    @classmethod
    def from_env(cls, env: Any) -> "RoadGraph":
        coords = {n: loc["coords"] for n, loc in env.state["locations"].items()}
        adj: dict[str, list[Edge]] = {n: [] for n in coords}
        for n in coords:
            for r in env.neighbours(n):
                adj[n].append(Edge(r["to"], r["distance_km"], env.edge_time_min(r), env.edge_energy_kwh(r),
                                   r["toll"], r["road_type"]))
        max_speed = max(r["speed_kmh"] for r in env.state["roads"])
        kwh = min((e.energy_kwh / e.distance_km for es in adj.values() for e in es if e.distance_km > 0),
                  default=env.vehicle["consumption_kwh_per_km"])
        factors = [r["distance_km"] / max(1e-9, haversine_km(coords[r["from"]], coords[r["to"]]))
                   for r in env.state["roads"]]
        return cls(coords, adj, max_speed, kwh, min(1.0, min(factors)) * 0.999)

    def straight_km(self, a: str, b: str) -> float:
        return haversine_km(self.coords[a], self.coords[b])

    def heuristic(self, weights: CostWeights, goal: str):
        """Admissible lower bound on the remaining cost (straight line, fastest road, cheapest energy)."""
        def h(n: str) -> float:
            d = self.straight_km(n, goal) * self.road_factor_min
            return (weights.time * d / self.max_speed_kmh * 60.0 + weights.distance * d
                    + weights.energy * d * self.min_kwh_per_km)
        return h

    def nodes(self) -> list[str]:
        return list(self.coords)
