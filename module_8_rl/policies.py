"""Baseline decision policies (module 8). All go through the same safety gate."""
from __future__ import annotations

from typing import Callable, Protocol

from contracts import ClarificationHistory, DecisionKind
from module_4_evpi import EVPIClarifier

from .environment import SAFE, Act, Situation


class Policy(Protocol):
    def decide(self, s: Situation) -> Act: ...


class AlwaysExecute:
    name = "always_execute"

    def decide(self, s: Situation) -> Act:
        return Act.EXECUTE


class AlwaysClarify:
    """Clarify whenever any uncertainty exists."""
    name = "always_clarify"

    def decide(self, s: Situation) -> Act:
        return Act.CLARIFY if len(s.belief.candidates) > 1 and s.top().prob < 0.99 and s.budget > 0 else Act.EXECUTE


class FixedThreshold:
    name = "fixed_threshold"

    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold

    def decide(self, s: Situation) -> Act:
        return Act.EXECUTE if s.top().prob >= self.threshold or s.budget <= 0 else Act.CLARIFY


class EVPIPolicy:
    """Module 4's EVPI clarifier without RL; ignores safety/feasibility (the gate handles it)."""
    name = "evpi"

    def __init__(self) -> None:
        self.clar = EVPIClarifier()

    def decide(self, s: Situation) -> Act:
        hist = ClarificationHistory(asked_params=[], budget=s.budget)
        res = {"tool"} if s.context_resolvable and not s.context_used else set()
        d = self.clar.decide(s.belief, hist, resolvable_params=res)
        return {DecisionKind.PROCEED: Act.EXECUTE, DecisionKind.ASK: Act.CLARIFY,
                DecisionKind.GATHER_CONTEXT: Act.GATHER_CONTEXT}[d.kind]


class HybridPolicy(EVPIPolicy):
    """EVPI for ambiguity + explicit rules for unsupported / infeasible / unsafe requests."""
    name = "hybrid_rules"

    def decide(self, s: Situation) -> Act:
        if not s.supported or not s.feasible:
            return Act.SUGGEST_ALTERNATIVE
        if s.safety != SAFE:
            return Act.DELAY if s.safety == "deferrable" else Act.REFUSE
        return super().decide(s)


def baselines() -> list[Policy]:
    return [AlwaysExecute(), AlwaysClarify(), FixedThreshold(0.8), EVPIPolicy(), HybridPolicy()]
