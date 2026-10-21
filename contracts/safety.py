"""Safety verdict: produced by module 9, consumed by module 10 (and respected by module 8)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Verdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    DEFER = "defer"
    CONFIRM = "confirm"  # allowed only after explicit user confirmation


class SafetyVerdict(BaseModel):
    verdict: Verdict
    reason: str
    step_id: str | None = None
