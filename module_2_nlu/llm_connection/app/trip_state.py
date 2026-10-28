
from pydantic import BaseModel, Field


class TripState(BaseModel):
    origin: str
    destination: str
    current_location: str
    battery_percent: float = Field(ge=0, le=100)
    estimated_range_km: float = Field(ge=0)
    current_route: list[dict] = Field(default_factory=list)
