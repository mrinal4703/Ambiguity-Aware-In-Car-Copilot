"""Decision policy: proceed, gather context internally, or ask the best question."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contracts import (
    BeliefState,
    ClarificationDecision,
    ClarificationHistory,
    DecisionKind,
)

from .evpi import (
    Phraser,
    answer_options,
    evpi,
    make_question,
    score_all,
    uncertain_parameters,
    update_with_answer,
)


@dataclass(frozen=True)
class ClarifierConfig:
    execute_threshold: float = 0.80   # proceed when the top candidate is at least this likely
    redundancy_lambda: float = 0.30   # penalty per repeat of the same question
    min_score: float = 0.05           # do not ask if the best question gains less than this
    budget: int = 3                   # max questions per dialogue


class EVPIClarifier:
    """Usage from the orchestrator:

        clar = EVPIClarifier()
        history = clar.new_history()
        decision = clar.decide(belief, history, resolvable_params={"recipient"})
        # ASK            -> show decision.question, then:
        #                   belief, history, ok = clar.apply_answer(belief, history, decision.parameter, answer)
        #                   (ok False -> answer not among candidates: re-parse with NLU)
        # GATHER_CONTEXT -> look up decision.parameter (calendar, vehicle state...), then:
        #                   belief, ok = clar.apply_context(belief, decision.parameter, value)
        #                   (if the lookup finds nothing, call decide again without that
        #                    parameter in resolvable_params)
        # PROCEED        -> pass decision.candidate_id to planning; the safety gate (module 9)
        #                   still has the final word.
    """

    def __init__(self, config: ClarifierConfig | None = None, phraser: Phraser | None = None):
        self.config = config or ClarifierConfig()
        self.phraser = phraser

    def new_history(self) -> ClarificationHistory:
        return ClarificationHistory(budget=self.config.budget)

    def decide(
        self,
        belief: BeliefState,
        history: ClarificationHistory,
        resolvable_params: frozenset[str] | set[str] = frozenset(),
    ) -> ClarificationDecision:
        cfg = self.config
        top = belief.top()

        if top.prob >= cfg.execute_threshold:
            return ClarificationDecision(
                kind=DecisionKind.PROCEED, candidate_id=top.id,
                reason=f"top candidate probability {top.prob:.2f} >= {cfg.execute_threshold:.2f}",
            )

        uncertain = uncertain_parameters(belief)
        if not uncertain:
            return ClarificationDecision(
                kind=DecisionKind.PROCEED, candidate_id=top.id,
                reason="candidates do not differ on any parameter",
            )

        # 1. Try to resolve internally before bothering the user.
        gatherable = [p for p in uncertain if p in resolvable_params]
        if gatherable:
            param = max(gatherable, key=lambda p: evpi(belief, p))
            return ClarificationDecision(
                kind=DecisionKind.GATHER_CONTEXT, parameter=param,
                reason=f"'{param}' can be looked up internally",
            )

        # 2. Budget.
        if history.remaining <= 0:
            return ClarificationDecision(
                kind=DecisionKind.PROCEED, candidate_id=top.id, budget_exhausted=True,
                reason="question budget exhausted; going with the most likely candidate",
            )

        # 3. Pick the question with the best net score.
        scores = score_all(belief, history, cfg.redundancy_lambda)
        best = max(scores, key=scores.get)
        if scores[best] < cfg.min_score:
            return ClarificationDecision(
                kind=DecisionKind.PROCEED, candidate_id=top.id, scores=scores,
                reason=f"best question score {scores[best]:.2f} < min_score {cfg.min_score:.2f}",
            )

        options = [v for v, _ in answer_options(belief, best)]
        return ClarificationDecision(
            kind=DecisionKind.ASK, parameter=best, scores=scores,
            question=make_question(best, options, phraser=self.phraser),
            options=[str(v) for v in options],
            reason=f"highest net score ({scores[best]:.2f}) on '{best}'",
        )

    def apply_answer(
        self, belief: BeliefState, history: ClarificationHistory, param: str, answer: Any
    ) -> tuple[BeliefState, ClarificationHistory, bool]:
        new_belief, matched = update_with_answer(belief, param, answer)
        new_history = history.model_copy(
            update={"asked_params": [*history.asked_params, param]}
        )
        return new_belief, new_history, matched

    def apply_context(
        self, belief: BeliefState, param: str, value: Any
    ) -> tuple[BeliefState, bool]:
        """Same as an answer but does not use up question budget."""
        return update_with_answer(belief, param, value)


def belief_features(belief: BeliefState, history: ClarificationHistory) -> dict[str, float]:
    """Numeric summary of uncertainty, intended as part of the RL state (module 8)."""
    return {
        "top_prob": belief.top().prob,
        "margin": belief.margin(),
        "entropy_bits": belief.entropy_bits(),
        "n_candidates": float(len(belief.candidates)),
        "n_uncertain_params": float(len(uncertain_parameters(belief))),
        "questions_asked": float(history.questions_asked),
        "budget_remaining": float(history.remaining),
    }
