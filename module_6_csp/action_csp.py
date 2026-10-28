"""Safe vehicle-control settings as a CSP (module 6, owner: Prasanna).

One variable (the setting value, e.g. window position or AC temperature) with a
finite domain. Hard constraints are the safety and validity limits for the current
situation (supplied by module 9); the soft preference is closeness to what the
driver asked for. The solver returns the closest value that satisfies every limit,
so the agent can offer a modified action instead of a flat refusal:

    "Opening the windows fully at 100 km/h is unsafe. Open them to 20% instead?"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Hashable

from .csp import CSP

Limit = tuple[str, Callable[[float], bool]]          # (name, predicate on the value)


@dataclass
class SettingResult:
    requested: float
    value: float | None                                # closest safe value, None if none exists
    violated: list[str] = field(default_factory=list)  # limits the request breaks
    modified: bool = False                             # value differs from the request

    @property
    def feasible(self) -> bool:
        return self.value is not None


def solve_setting(requested: float, domain: list[Hashable], limits: list[Limit]) -> SettingResult:
    csp = CSP(["value"], {"value": list(domain)})
    for name, pred in limits:
        csp.add(name, ("value",), pred)
    violated = [name for name, pred in limits if not pred(requested)]
    if not violated:
        return SettingResult(requested, requested, [], False)
    sols, _, _ = csp.solve(all_solutions=True)
    if not sols:
        return SettingResult(requested, None, violated, False)
    best = min((s["value"] for s in sols), key=lambda v: (abs(v - requested), v))
    return SettingResult(requested, best, violated, True)


def window_domain(step: int = 5) -> list[int]:
    return list(range(0, 101, step))


def ac_domain(lo: float = 10.0, hi: float = 35.0, step: float = 0.5) -> list[float]:
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 1) for i in range(n + 1)]
