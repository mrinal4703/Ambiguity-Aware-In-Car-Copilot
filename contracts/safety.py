"""Safety verdict: produced by module 9, consumed by module 10 (and respected by module 8)."""
from __future__ import annotations

from enum import Enum

from typing import Any

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
    # a safer version of the request (e.g. windows 20 % instead of 100 % at highway speed);
    # with CONFIRM it means "do this instead?", and the executor uses it once the driver agrees
    modified_params: dict[str, Any] | None = None
