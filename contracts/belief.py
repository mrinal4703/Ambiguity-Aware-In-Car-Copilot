"""Belief state: produced by module 3 (uncertainty), consumed by modules 4 and 8."""
from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Candidate(BaseModel):
    """One possible interpretation of the user's request as a tool call."""

    id: str
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    prob: float = Field(ge=0.0)


class BeliefState(BaseModel):
    """Candidate interpretations with probabilities.

    Probabilities are renormalised to sum to 1 on construction.
    """

    candidates: list[Candidate]

    @model_validator(mode="after")
    def _normalise(self) -> "BeliefState":
        if not self.candidates:
            raise ValueError("BeliefState needs at least one candidate")
        ids = [c.id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("candidate ids must be unique")
        total = sum(c.prob for c in self.candidates)
        if total <= 0:
            raise ValueError("candidate probabilities must sum to > 0")
        if abs(total - 1.0) > 1e-9:
            self.candidates = [
                c.model_copy(update={"prob": c.prob / total}) for c in self.candidates
            ]
        return self

    def ranked(self) -> list[Candidate]:
        return sorted(self.candidates, key=lambda c: -c.prob)

    def top(self) -> Candidate:
        return self.ranked()[0]

    def margin(self) -> float:
        """Top probability minus the runner-up (top prob if only one candidate)."""
        r = self.ranked()
        return r[0].prob - (r[1].prob if len(r) > 1 else 0.0)

    def entropy_bits(self) -> float:
        return -sum(c.prob * math.log2(c.prob) for c in self.candidates if c.prob > 0)


class ClarificationHistory(BaseModel):
    """What has already been asked in this dialogue (for redundancy and budget)."""

    asked_params: list[str] = Field(default_factory=list)
    budget: int = 3

    @property
    def questions_asked(self) -> int:
        return len(self.asked_params)

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.questions_asked)
