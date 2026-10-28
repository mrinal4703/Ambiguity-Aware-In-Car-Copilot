"""Module 4: EVPI-based clarification (owner: Mrinal).

Takes a BeliefState (module 3) and decides: proceed, ask a question, or gather context.
"""
from .answer_matching import match_answer
from .baselines import ALL_POLICIES, AlwaysClarify, AlwaysExecute, FixedThreshold, evpi_policy
from .clarifier import RISK_OF_TOOL, ClarifierConfig, EVPIClarifier, belief_features, risk_of
from .evpi import (
    TOOL_PARAM,
    answer_options,
    evpi,
    make_question,
    score_all,
    uncertain_parameters,
    update_with_answer,
    update_with_noisy_answer,
)
from .utility_evpi import default_utility, expected_utility_now, utility_evpi, utility_scores

__all__ = [
    "match_answer", "ALL_POLICIES", "AlwaysClarify", "AlwaysExecute", "FixedThreshold", "evpi_policy",
    "ClarifierConfig", "EVPIClarifier", "belief_features", "RISK_OF_TOOL", "risk_of",
    "TOOL_PARAM", "answer_options", "evpi", "make_question", "score_all",
    "uncertain_parameters", "update_with_answer", "update_with_noisy_answer",
    "default_utility", "expected_utility_now", "utility_evpi", "utility_scores",
]
