"""Reproducible initial states used by tests, RL training and evaluation scenarios."""
from __future__ import annotations

from typing import Any, Callable

from .world import default_state


def _default(s: dict[str, Any]) -> None:
    pass


def _low_battery(s: dict[str, Any]) -> None:
    s["vehicle"]["battery_pct"] = 12.0          # about 24 km of range


def _critical_battery(s: dict[str, Any]) -> None:
    s["vehicle"]["battery_pct"] = 3.0           # about 6 km: hardly anything reachable


def _highway(s: dict[str, Any]) -> None:
    s["vehicle"]["speed_kmh"] = 100.0
    s["vehicle"]["location"] = "nh16_junction"
    s["driving"]["road_type"] = "highway"


def _parked(s: dict[str, Any]) -> None:
    s["vehicle"]["speed_kmh"] = 0.0
    s["vehicle"]["gear"] = "P"


def _storm(s: dict[str, Any]) -> None:
    s["driving"].update({"weather": "rain", "traffic": "heavy", "driving_difficulty": "high"})


def _cool_cabin(s: dict[str, Any]) -> None:
    s["vehicle"]["cabin_temperature_c"] = 22.0
    s["driving"]["outside_temperature_c"] = 20.0


def _no_windows_feature(s: dict[str, Any]) -> None:
    s["vehicle"]["features"].remove("windows")


PRESETS: dict[str, Callable[[dict[str, Any]], None]] = {
    "default": _default, "low_battery": _low_battery, "critical_battery": _critical_battery,
    "highway": _highway, "parked": _parked, "storm": _storm, "cool_cabin": _cool_cabin,
    "no_windows_feature": _no_windows_feature,
}


def make_state(*presets: str) -> dict[str, Any]:
    """`make_state("low_battery", "storm")` -> a fresh state with those presets applied in order."""
    s = default_state()
    for p in presets or ("default",):
        PRESETS[p](s)
    return s
