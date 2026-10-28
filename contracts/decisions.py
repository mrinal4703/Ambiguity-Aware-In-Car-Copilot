"""Output of module 4 (EVPI clarification), consumed by the orchestrator and module 8."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DecisionKind(str, Enum):
    PROCEED = "proceed"                 # go ahead with candidate_id (safety gate still applies)
    ASK = "ask"                         # ask the user `question`
    GATHER_CONTEXT = "gather_context"   # look `parameter` up internally first


class ClarificationDecision(BaseModel):
    kind: DecisionKind
    reason: str
    candidate_id: str | None = None
    parameter: str | None = None
    question: str | None = None
    options: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)  # parameter -> net score
    budget_exhausted: bool = False
