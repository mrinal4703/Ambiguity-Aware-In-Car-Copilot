"""EVPI scoring, question generation and belief updates.

Definition used here (the simplified one in the project PDF):

    EVPI(q)  = expected best-candidate probability after hearing the answer
               - best-candidate probability now
    Score(q) = EVPI(q) - lambda * Redundancy(q)

Assumption: the user answers truthfully with one of the candidate values.
Each question targets one parameter. The candidate's tool name is treated as the
pseudo-parameter "tool" so intent-level ambiguity is handled the same way.

NOTE: this is a probability-gain proxy, not utility-based EVPI. Compare with the
definition in Suri et al. (2026) before using it in a formal report.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from contracts import BeliefState, ClarificationHistory

TOOL_PARAM = "tool"

Phraser = Callable[[str, list[str]], str]
Labeler = Callable[[str, Any], str]   # (param, value) -> human-readable option label


def _value(candidate, param: str) -> Any:
    return candidate.tool if param == TOOL_PARAM else candidate.params.get(param)


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def uncertain_parameters(belief: BeliefState) -> list[str]:
    """Parameters (incl. 'tool') on which the candidates disagree."""
    params = [TOOL_PARAM] + sorted({p for c in belief.candidates for p in c.params})
    return [
        p for p in params
        if len({_key(_value(c, p)) for c in belief.candidates}) > 1
    ]


def answer_options(belief: BeliefState, param: str) -> list[tuple[Any, float]]:
    """Possible answers for `param` with their probability mass, most likely first."""
    mass: dict[str, float] = {}
    original: dict[str, Any] = {}
    for c in belief.candidates:
        k = _key(_value(c, param))
        mass[k] = mass.get(k, 0.0) + c.prob
        original.setdefault(k, _value(c, param))
    return sorted(((original[k], m) for k, m in mass.items()), key=lambda t: -t[1])


def expected_best_after(belief: BeliefState, param: str) -> float:
    """Sum over answers of P(answer) * (best posterior given that answer)."""
    best: dict[str, float] = {}
    for c in belief.candidates:
        k = _key(_value(c, param))
        best[k] = max(best.get(k, 0.0), c.prob)
    return sum(best.values())


def evpi(belief: BeliefState, param: str) -> float:
    return max(0.0, expected_best_after(belief, param) - belief.top().prob)


def redundancy(param: str, history: ClarificationHistory) -> float:
    """How many times this parameter was already asked about."""
    return float(history.asked_params.count(param))


def score_all(
    belief: BeliefState, history: ClarificationHistory, lam: float
) -> dict[str, float]:
    return {
        p: evpi(belief, p) - lam * redundancy(p, history)
        for p in uncertain_parameters(belief)
    }


def update_with_answer(
    belief: BeliefState, param: str, answer: Any
) -> tuple[BeliefState, bool]:
    """Keep candidates consistent with the answer and renormalise.

    Returns (new_belief, matched). If the answer matches no candidate, the belief is
    returned unchanged with matched=False: the caller should re-parse the user's
    reply with the NLU module (the true meaning is outside the candidate set).
    """
    kept = [c for c in belief.candidates if _key(_value(c, param)) == _key(answer)]
    if not kept:
        return belief, False
    return BeliefState(candidates=kept), True


def _label(param: str, value: Any) -> str:
    if value is None:
        return "none of these"
    text = str(value)
    return text.replace("_", " ") if param == TOOL_PARAM else text


def make_question(
    param: str,
    options: list[Any],
    max_options: int = 3,
    phraser: Phraser | None = None,
    labeler: Labeler | None = None,
) -> str:
    """Template question. Pass `phraser` to let an LLM word it more naturally and
    `labeler` to show friendly labels (e.g. contact names instead of ids)."""
    shown = [(labeler(param, v) if labeler and v is not None else _label(param, v)) for v in options[:max_options]]
    if phraser is not None:
        return phraser(param, shown)
    extra = len(options) > max_options
    listing = ", ".join(shown[:-1]) + (" or " if len(shown) > 1 else "") + shown[-1]
    if extra:
        listing += ", or something else"
    if param == TOOL_PARAM:
        return f"What would you like me to do: {listing}?"
    noun = {"recipient": "recipient", "destination": "destination", "near": "area"}.get(param, param.replace("_", " "))
    return f"Which {noun} do you mean: {listing}?"


def update_with_noisy_answer(
    belief: BeliefState, param: str, answer: Any, reliability: float = 0.9
) -> tuple[BeliefState, bool]:
    """Bayesian update when the answer may be wrong (misheard / misspoken).

    P(answer | candidate) = reliability            if the candidate has that value
                          = (1 - reliability) / (k - 1)   otherwise (k = number of distinct values)
    Unlike `update_with_answer`, no candidate is eliminated outright.
    """
    values = {_key(_value(c, param)) for c in belief.candidates}
    if _key(answer) not in values:
        return belief, False
    k = len(values)
    miss = (1 - reliability) / (k - 1) if k > 1 else 0.0
    cands = [c.model_copy(update={"prob": c.prob * (reliability if _key(_value(c, param)) == _key(answer) else miss)})
             for c in belief.candidates]
    cands = [c for c in cands if c.prob > 0]
    return BeliefState(candidates=cands), True
