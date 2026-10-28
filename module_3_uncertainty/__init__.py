"""Module 3: uncertainty estimation (owner: Swastika).

NLU tasks (module 2) -> calibrated, context-grounded `BeliefState` (contract) plus an
`UncertaintyReport` that separates request ambiguity from model uncertainty.
"""
from .belief_builder import BeliefBuilder, BeliefBundle, UncertaintyReport, context_weight, goal_of, tool_name
from .calibration import apply_temperature, expected_calibration_error, fit_temperature, nll
from .context_resolver import Alternative, ContextResolver

__all__ = ["BeliefBuilder", "BeliefBundle", "UncertaintyReport", "context_weight", "goal_of", "tool_name",
           "apply_temperature", "expected_calibration_error", "fit_temperature", "nll",
           "Alternative", "ContextResolver"]
