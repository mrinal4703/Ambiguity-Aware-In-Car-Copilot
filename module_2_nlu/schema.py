"""Structured NLU output (module 2).

The NLU never executes anything. It turns an utterance into one or more `Task`s,
each with several weighted `GoalCandidate`s. Module 3 turns these into a
`BeliefState`; parameters that start with "@" are *references* that module 3
resolves from context (calendar, contacts, vehicle state).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Goal vocabulary shared with module 3 (beliefs) and module 7 (planning).
GOALS: dict[str, list[str]] = {
    "navigate":       ["destination"],
    "find_charging":  ["near"],
    "find_poi":       ["category", "near"],
    "send_message":   ["recipient", "text"],
    "call_contact":   ["recipient"],
    "climate":        [],               # on / temperature_c / delta_c
    "windows":        ["position"],
    "media":          [],
    "video":          [],
    "reminder":       ["text"],
    "info_calendar":  [],
    "info_vehicle":   [],
    "info_traffic":   [],
    "info_eta":       [],
    "chat":           [],               # keep the driver company (e.g. when tired); no vehicle tool
    "unsupported":    ["feature"],
}

# Reference placeholders module 3 knows how to resolve.
REFERENCES = {
    "@next_event_location": "location of the next calendar event",
    "@next_event_people": "organizer/attendees of the next calendar event",
    "@current_route": "the active route or current location",
    "@current_destination": "destination of the active navigation",
}


class GoalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str
    params: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(ge=0.0)
    rationale: str = ""


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    rewritten: str
    intent: str
    candidates: list[GoalCandidate] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    urgency: Literal["low", "normal", "high"] = "normal"
    explicit_action: bool = False
    requires_context: bool = False
    missing_params: list[str] = Field(default_factory=list)


class NLUResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    utterance: str
    tasks: list[Task]
    parser: str = "rules"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    notes: list[str] = Field(default_factory=list)


def validate_result(result: NLUResult) -> list[str]:
    """Own checks on top of the schema (the LLM output is never trusted blindly)."""
    issues = []
    for t in result.tasks:
        for c in t.candidates:
            if c.goal not in GOALS:
                issues.append(f"unknown goal '{c.goal}'")
            for p in GOALS.get(c.goal, []):
                if p not in c.params:
                    issues.append(f"goal '{c.goal}' missing parameter '{p}' (use null if unknown)")
    return issues
