"""Non-learning clarification policies to compare against (module 4, milestone M4.6).

All share the interface  policy.decide(belief, history, resolvable_params) -> ClarificationDecision.
"""
from __future__ import annotations

from contracts import BeliefState, ClarificationDecision, ClarificationHistory, DecisionKind

from .clarifier import ClarifierConfig, EVPIClarifier
from .evpi import TOOL_PARAM, answer_options, make_question, uncertain_parameters


class AlwaysExecute:
    """Always proceed with the most probable interpretation."""
    name = "always_execute"

    def decide(self, belief: BeliefState, history: ClarificationHistory, resolvable_params=frozenset(), **_):
        return ClarificationDecision(kind=DecisionKind.PROCEED, candidate_id=belief.top().id,
                                     reason="baseline: always execute the top candidate")


class AlwaysClarify:
    """Ask whenever any uncertainty exists (first uncertain parameter, tool first), within budget."""
    name = "always_clarify"

    def decide(self, belief: BeliefState, history: ClarificationHistory, resolvable_params=frozenset(), **_):
        unc = uncertain_parameters(belief)
        if not unc or history.remaining <= 0:
            return ClarificationDecision(kind=DecisionKind.PROCEED, candidate_id=belief.top().id,
                                         budget_exhausted=bool(unc), reason="baseline: nothing left to ask")
        param = TOOL_PARAM if TOOL_PARAM in unc else unc[0]
        if param in history.asked_params:
            rest = [p for p in unc if p not in history.asked_params]
            param = rest[0] if rest else param
        opts = [v for v, _ in answer_options(belief, param)]
        return ClarificationDecision(kind=DecisionKind.ASK, parameter=param, options=[str(o) for o in opts],
                                     question=make_question(param, opts), reason="baseline: always clarify")


class FixedThreshold:
    """Proceed above a confidence threshold, otherwise ask about the first uncertain parameter."""
    name = "fixed_threshold"

    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold
        self._ask = AlwaysClarify()

    def decide(self, belief: BeliefState, history: ClarificationHistory, resolvable_params=frozenset(), **_):
        if belief.top().prob >= self.threshold:
            return ClarificationDecision(kind=DecisionKind.PROCEED, candidate_id=belief.top().id,
                                         reason=f"baseline: top >= {self.threshold}")
        return self._ask.decide(belief, history)


def evpi_policy(config: ClarifierConfig | None = None) -> EVPIClarifier:
    c = EVPIClarifier(config)
    c.name = "evpi"  # type: ignore[attr-defined]
    return c


ALL_POLICIES = {"always_execute": AlwaysExecute, "always_clarify": AlwaysClarify,
                "fixed_threshold": FixedThreshold, "evpi": evpi_policy}
