"""A* search (module 5) with an admissible straight-line heuristic."""
from __future__ import annotations

from .graph import CostWeights, RoadGraph
from .uniform_cost import SearchResult, best_first


def astar(graph: RoadGraph, start: str, goal: str, weights: CostWeights = CostWeights()) -> SearchResult:
    return best_first(graph, start, goal, weights, graph.heuristic(weights, goal))
