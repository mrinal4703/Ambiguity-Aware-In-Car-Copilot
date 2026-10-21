"""Module 4: EVPI-based clarification.

Takes a BeliefState (module 3) and decides: proceed, ask a question, or gather context.
"""
from .clarifier import ClarifierConfig, EVPIClarifier, belief_features
from .evpi import (
    TOOL_PARAM,
    evpi,
    make_question,
    score_all,
    uncertain_parameters,
    update_with_answer,
)

__all__ = [
    "ClarifierConfig", "EVPIClarifier", "belief_features",
    "TOOL_PARAM", "evpi", "make_question", "score_all",
    "uncertain_parameters", "update_with_answer",
]
