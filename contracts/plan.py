"""Plan shapes: produced by module 7, checked by module 9, executed by module 10."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .tools import SafetyClass


class PlanStep(BaseModel):
    id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)  # ids of earlier steps
    safety_class: SafetyClass = SafetyClass.LOW
    recovery: str | None = None


class Plan(BaseModel):
    goal: str
    steps: list[PlanStep]
