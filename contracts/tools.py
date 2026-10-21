"""Tool description: produced by module 1 (simulator), used by modules 2, 7, 9."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SafetyClass(str, Enum):
    LOW = "low"                      # may be proactive (e.g. read-only lookups)
    CONSEQUENTIAL = "consequential"  # needs confirmation (e.g. send message, change route)
    CRITICAL = "critical"            # driving-safety relevant (e.g. window or seat control while moving)


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)  # name -> type/description
    required: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    safety_class: SafetyClass = SafetyClass.LOW
    requires_confirmation: bool = False
