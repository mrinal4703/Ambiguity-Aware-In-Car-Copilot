"""Route shapes: module 5 produces RouteOption, module 6 produces FeasibilityResult."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RouteOption(BaseModel):
    id: str
    waypoints: list[str]
    distance_km: float
    time_min: float
    energy_kwh: float | None = None
    cost: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeasibilityResult(BaseModel):
    route_id: str
    feasible: bool
    violated_constraints: list[str] = Field(default_factory=list)
    notes: str = ""
