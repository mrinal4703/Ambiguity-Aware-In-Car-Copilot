"""Forward state-space planner (breadth-first over STRIPS facts) -> contracts.Plan."""
from __future__ import annotations

from collections import deque
from typing import Any

from contracts import Plan, PlanStep

from .actions import Action, UnsupportedGoal, domain_for, initial_facts


class NoPlan(RuntimeError):
    pass


def forward_search(actions: list[Action], start: frozenset[str], goal: frozenset[str],
                   max_depth: int = 12) -> tuple[list[Action], int]:
    """BFS over fact sets. Returns the shortest action sequence and number of states expanded."""
    frontier = deque([(start, [])])
    seen = {start}
    expanded = 0
    while frontier:
        facts, plan = frontier.popleft()
        if goal <= facts:
            return plan, expanded
        if len(plan) >= max_depth:
            continue
        expanded += 1
        for a in actions:
            if a.applicable(facts) and a.key not in {x.key for x in plan}:
                nxt = a.apply(facts)
                if nxt != facts and nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, plan + [a]))
    raise NoPlan(f"no plan reaches {sorted(goal)}")


def to_plan(goal: str, seq: list[Action], start: frozenset[str]) -> Plan:
    """Turn an action sequence into PlanSteps with explicit dependencies."""
    steps: list[PlanStep] = []
    producer: dict[str, str] = {}
    for i, a in enumerate(seq, 1):
        sid = f"s{i}"
        deps = sorted({producer[f] for f in a.pre if f in producer})
        # parameter references also create dependencies
        for v in a.params.values():
            for ref in (v if isinstance(v, list) else [v]):
                if isinstance(ref, str) and ref.startswith("$"):
                    src = ref[1:].split(".")[0]
                    deps += [s.id for s in steps if s.action == src and s.id not in deps]
        steps.append(PlanStep(id=sid, action=a.name, params=dict(a.params), preconditions=sorted(a.pre),
                              effects=sorted(a.add), depends_on=sorted(set(deps)), safety_class=a.safety_class,
                              recovery=a.recovery))
        for f in a.add:
            producer[f] = sid
    return Plan(goal=goal, steps=steps)


class Planner:
    """plan(goal, params, env, context) -> Plan (raises UnsupportedGoal / NoPlan)."""

    def __init__(self, max_depth: int = 12):
        self.max_depth = max_depth
        self.last_expanded = 0

    def plan(self, goal: str, params: dict[str, Any], env: Any, context: dict[str, Any] | None = None,
             facts: frozenset[str] | None = None) -> Plan:
        actions, goal_facts = domain_for(goal, params, env, context)
        start = facts if facts is not None else initial_facts(env)
        seq, self.last_expanded = forward_search(actions, start, goal_facts, self.max_depth)
        return to_plan(goal, seq, start)


__all__ = ["Planner", "NoPlan", "UnsupportedGoal", "forward_search", "to_plan"]
