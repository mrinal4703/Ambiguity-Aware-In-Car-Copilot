"""Reward table (module 8, owner: Jana). Values from the project PDF, kept configurable."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RewardConfig:
    task_success: float = 10.0          # correct, safe task completion
    useful_clarification: float = 2.0
    unnecessary_clarification: float = -2.0
    infeasible_proposal: float = -5.0   # executing something infeasible / wrong interpretation
    unsafe_attempt: float = -20.0       # trying to execute an unsafe action (caught by the gate)
    fabricated_result: float = -20.0    # reporting success that did not happen
    correct_handling: float = 8.0       # right refusal / delay / alternative for a non-executable request
    weak_handling: float = 3.0          # acceptable but not ideal (e.g. refusing instead of suggesting)
    context_cost: float = -0.5          # small cost of a context lookup
    wasted_step: float = -1.0
    timeout: float = -5.0

    def with_(self, **kw: float) -> "RewardConfig":
        return replace(self, **kw)


DEFAULT_REWARDS = RewardConfig()

# Variants used for the reward-sensitivity study.
SENSITIVITY = {
    "default": DEFAULT_REWARDS,
    "cheap_questions": DEFAULT_REWARDS.with_(unnecessary_clarification=-0.5, useful_clarification=3.0),
    "costly_questions": DEFAULT_REWARDS.with_(unnecessary_clarification=-5.0, useful_clarification=0.5),
    "harsh_mistakes": DEFAULT_REWARDS.with_(infeasible_proposal=-15.0),
    "mild_mistakes": DEFAULT_REWARDS.with_(infeasible_proposal=-2.0),
}
