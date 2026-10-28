"""Uniform-Cost Search (module 5): optimal for non-negative edge costs."""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable

from .graph import CostWeights, Edge, RoadGraph


@dataclass
class SearchResult:
    path: list[str] | None
    cost: float
    expanded: int
    edges: list[Edge] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.path is not None


def _reconstruct(prev: dict[str, tuple[str, Edge]], start: str, goal: str) -> tuple[list[str], list[Edge]]:
    path, edges, n = [goal], [], goal
    while n != start:
        p, e = prev[n]
        edges.append(e)
        path.append(p)
        n = p
    return path[::-1], edges[::-1]


def best_first(graph: RoadGraph, start: str, goal: str, weights: CostWeights,
               h: Callable[[str], float] | None = None) -> SearchResult:
    """Shared engine: h=None gives UCS, an admissible h gives A*."""
    h = h or (lambda n: 0.0)
    g = {start: 0.0}
    prev: dict[str, tuple[str, Edge]] = {}
    frontier = [(h(start), 0, start)]
    closed: set[str] = set()
    tie = 0
    expanded = 0
    while frontier:
        _, _, n = heapq.heappop(frontier)
        if n in closed:
            continue
        if n == goal:
            path, edges = _reconstruct(prev, start, goal)
            return SearchResult(path, g[n], expanded, edges)
        closed.add(n)
        expanded += 1
        for e in graph.adj.get(n, []):
            c = weights.edge_cost(e)
            if c == float("inf"):
                continue
            ng = g[n] + c
            if ng < g.get(e.to, float("inf")):
                g[e.to] = ng
                prev[e.to] = (n, e)
                tie += 1
                heapq.heappush(frontier, (ng + h(e.to), tie, e.to))
    return SearchResult(None, float("inf"), expanded)


def uniform_cost_search(graph: RoadGraph, start: str, goal: str,
                        weights: CostWeights = CostWeights()) -> SearchResult:
    return best_first(graph, start, goal, weights, None)
