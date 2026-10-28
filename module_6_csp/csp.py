"""A small generic CSP solver: backtracking + forward checking + MRV (module 6).

Constraints are (name, scope, predicate). A constraint is checked as soon as all
variables in its scope are assigned. Forward checking prunes the domains of
unassigned variables whose constraints become fully assigned with that value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Hashable

Assignment = dict[str, Any]


@dataclass
class Constraint:
    name: str
    scope: tuple[str, ...]
    predicate: Callable[..., bool]
    hard: bool = True

    def satisfied(self, a: Assignment) -> bool:
        return self.predicate(*(a[v] for v in self.scope))


@dataclass
class SearchStats:
    nodes: int = 0
    backtracks: int = 0
    pruned: int = 0
    checks: int = 0


@dataclass
class CSP:
    variables: list[str]
    domains: dict[str, list[Hashable]]
    constraints: list[Constraint] = field(default_factory=list)

    def add(self, name: str, scope: tuple[str, ...], predicate: Callable[..., bool]) -> None:
        self.constraints.append(Constraint(name, scope, predicate))

    def _relevant(self, var: str) -> list[Constraint]:
        return [c for c in self.constraints if var in c.scope]

    def violations(self, a: Assignment, stats: SearchStats | None = None) -> list[str]:
        out = []
        for c in self.constraints:
            if all(v in a for v in c.scope):
                if stats:
                    stats.checks += 1
                if not c.satisfied(a):
                    out.append(c.name)
        return out

    def node_consistent(self) -> tuple[dict[str, list[Hashable]], dict[str, dict[Hashable, list[str]]]]:
        """Apply unary constraints; return pruned domains and why each value was removed."""
        doms = {v: list(d) for v, d in self.domains.items()}
        why: dict[str, dict[Hashable, list[str]]] = {v: {} for v in self.variables}
        for c in self.constraints:
            if len(c.scope) == 1:
                v = c.scope[0]
                keep = []
                for x in doms[v]:
                    if c.predicate(x):
                        keep.append(x)
                    else:
                        why[v].setdefault(x, []).append(c.name)
                doms[v] = keep
        return doms, why

    def solve(self, all_solutions: bool = True, forward_checking: bool = True, mrv: bool = True,
              limit: int = 10_000) -> tuple[list[Assignment], SearchStats, dict[str, dict[Hashable, list[str]]]]:
        doms, why = self.node_consistent()
        stats = SearchStats()
        sols: list[Assignment] = []
        multi = [c for c in self.constraints if len(c.scope) > 1]

        def consistent(a: Assignment, var: str) -> bool:
            for c in multi:
                if var in c.scope and all(v in a for v in c.scope):
                    stats.checks += 1
                    if not c.satisfied(a):
                        return False
            return True

        def forward(a: Assignment, var: str, d: dict[str, list[Hashable]]) -> dict[str, list[Hashable]] | None:
            nd = {k: list(v) for k, v in d.items()}
            for other in self.variables:
                if other in a:
                    continue
                keep = []
                for x in nd[other]:
                    a[other] = x
                    ok = consistent(a, other)
                    del a[other]
                    if ok:
                        keep.append(x)
                    else:
                        stats.pruned += 1
                if not keep:
                    return None
                nd[other] = keep
            return nd

        def select(a: Assignment, d: dict[str, list[Hashable]]) -> str:
            free = [v for v in self.variables if v not in a]
            return min(free, key=lambda v: (len(d[v]), self.variables.index(v))) if mrv else free[0]

        def bt(a: Assignment, d: dict[str, list[Hashable]]) -> bool:
            if len(a) == len(self.variables):
                sols.append(dict(a))
                return not all_solutions or len(sols) >= limit
            var = select(a, d)
            for x in d[var]:
                stats.nodes += 1
                a[var] = x
                if consistent(a, var):
                    nd = forward(a, var, d) if forward_checking else d
                    if nd is not None and bt(a, nd):
                        return True
                del a[var]
                stats.backtracks += 1
            return False

        if all(doms[v] for v in self.variables):
            bt({}, doms)
        return sols, stats, why
