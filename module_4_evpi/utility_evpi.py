"""Utility-based EVPI (module 4 extension), for comparison with the probability-gain proxy.

Decision: execute one candidate. Utility U(chosen, true) = 1 if chosen == true,
else `wrong_cost` (negative for consequential tools, e.g. a message to the wrong
person). Asking about parameter q partitions candidates by their q-value:

    EU_now      = max_i sum_j p_j U(i, j)
    EU_after(q) = sum_v P(v) * max_i sum_{j: q_j = v} p(j | v) U(i, j)
    EVPI_u(q)   = EU_after(q) - EU_now   (>= 0)

With wrong_cost = 0 this reduces exactly to the probability-gain EVPI in evpi.py.
"""
from __future__ import annotations

from typing import Callable

from contracts import BeliefState, Candidate

from .evpi import _key, _value, uncertain_parameters

UtilityFn = Callable[[Candidate, Candidate], float]


def default_utility(wrong_cost: float = -1.0) -> UtilityFn:
    def u(chosen: Candidate, true: Candidate) -> float:
        return 1.0 if chosen.id == true.id else wrong_cost
    return u


def expected_utility_now(belief: BeliefState, utility: UtilityFn) -> float:
    cs = belief.candidates
    return max(sum(t.prob * utility(c, t) for t in cs) for c in cs)


def utility_evpi(belief: BeliefState, param: str, utility: UtilityFn) -> float:
    groups: dict[str, list[Candidate]] = {}
    for c in belief.candidates:
        groups.setdefault(_key(_value(c, param)), []).append(c)
    after = 0.0
    for members in groups.values():
        pv = sum(m.prob for m in members)
        best = max(sum((t.prob / pv) * utility(c, t) for t in members) for c in members)
        after += pv * best
    return max(0.0, after - expected_utility_now(belief, utility))


def utility_scores(belief: BeliefState, utility: UtilityFn) -> dict[str, float]:
    return {p: utility_evpi(belief, p, utility) for p in uncertain_parameters(belief)}
