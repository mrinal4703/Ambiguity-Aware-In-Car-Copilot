
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    value: Any
    source: Literal["explicit", "inferred", "context"]


class Ambiguity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_ambiguous: bool = False
    reason: Optional[str] = None
    clarification_question: Optional[str] = None


class ActionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True


class CapabilityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_actions: list[ActionCandidate] = Field(
        default_factory=list
    )
    unsupported_actions: list[ActionCandidate] = Field(
        default_factory=list
    )


class Reflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    issues: list[str] = Field(default_factory=list)


class IntentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    utterance: str
    rewritten_request: str
    entities: list[Entity] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    action_candidates: list[ActionCandidate] = Field(
        default_factory=list
    )
    context_references: list[str] = Field(default_factory=list)
    ambiguity: Ambiguity = Field(default_factory=Ambiguity)
    confidence: float = Field(ge=0.0, le=1.0)

    capability_check: Optional[CapabilityCheck] = None
    reflection: Optional[Reflection] = None
