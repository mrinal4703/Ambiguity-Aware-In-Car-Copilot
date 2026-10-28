"""Probabilistic beliefs about the world (module 3, owner: Swastika).

The problem statement asks for beliefs not only about what the driver means but
also about road conditions, travel time, charging-station availability and battery
status. Each belief is a small conjugate Bayesian model that is updated from
observations the copilot actually makes (tool results, driving progress):

  StationBelief      Beta(a, b) on "station is available when we get there"
                     prior from the station's live status and a reliability prior,
                     updated by every get_station_status / failed stop.
  BatteryBelief      Normal belief on the consumption factor phi
                     (real energy = model energy x phi), prior N(1, 0.1^2),
                     updated from (expected, actual) energy of every driven stretch.
                     Gives P(reach a destination with the reserve) and a cautious
                     phi_q to plan with.
  TravelTimeBelief   log-normal-ish multiplicative delay per road, prior from the
                     traffic level and weather, updated from live traffic incidents
                     and observed driving times. Gives mean/sd of a route time and
                     P(arrive before a deadline).
  RoadBelief         Beta on "road is congested/closed", prior from traffic and
                     weather, updated from live traffic and closures seen.

`WorldBelief` bundles them, `observe_*` methods update them and `summary()` feeds
the dashboard. Module 6 (CSP) and module 7 (planning) use phi_q, the availability
probabilities and P(on time) when they choose stations and check range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

TRAFFIC_MEAN = {"light": 1.0, "moderate": 1.2, "heavy": 1.6}


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class StationBelief:
    a: float
    b: float

    @property
    def p_available(self) -> float:
        return self.a / (self.a + self.b)

    def observe(self, available: bool, weight: float = 1.0) -> None:
        if available:
            self.a += weight
        else:
            self.b += weight


@dataclass
class BatteryBelief:
    mean: float = 1.0          # consumption factor phi
    var: float = 0.10 ** 2
    obs_var: float = 0.08 ** 2
    n: int = 0

    @property
    def sd(self) -> float:
        return math.sqrt(self.var)

    def observe(self, expected_kwh: float, actual_kwh: float) -> None:
        """Conjugate normal update with the observed ratio actual/expected."""
        if expected_kwh <= 0.05:
            return
        ratio = actual_kwh / expected_kwh
        # longer stretches are more informative
        ov = self.obs_var / max(0.25, min(4.0, expected_kwh))
        k = self.var / (self.var + ov)
        self.mean += k * (ratio - self.mean)
        self.var = (1 - k) * self.var
        self.n += 1

    def quantile(self, q: float = 0.9) -> float:
        z = {0.5: 0.0, 0.8: 0.842, 0.9: 1.282, 0.95: 1.645}.get(q, 1.282)
        return self.mean + z * self.sd

    def p_reach(self, model_energy_kwh: float, usable_kwh: float) -> float:
        """P(phi * model_energy <= usable energy)."""
        if model_energy_kwh <= 0:
            return 1.0
        threshold = usable_kwh / model_energy_kwh
        return _phi((threshold - self.mean) / self.sd)


@dataclass
class TravelTimeBelief:
    base_factor: float = 1.2
    sd_frac: float = 0.15
    road_factor: dict[frozenset, float] = field(default_factory=dict)

    def factor(self, a: str, b: str) -> float:
        return self.road_factor.get(frozenset((a, b)), 1.0)

    def route_time(self, legs: list[tuple[str, str, float]]) -> tuple[float, float]:
        """legs: (a, b, nominal minutes). Returns (mean, sd) minutes."""
        mean = sum(t * self.factor(a, b) for a, b, t in legs)
        sd = math.sqrt(sum((t * self.factor(a, b) * self.sd_frac) ** 2 for a, b, t in legs))
        return mean, sd

    def p_on_time(self, legs: list[tuple[str, str, float]], available_min: float, extra_min: float = 0.0) -> float:
        mean, sd = self.route_time(legs)
        return _phi((available_min - extra_min - mean) / max(sd, 1e-6))

    def observe_delay(self, a: str, b: str, factor: float) -> None:
        key = frozenset((a, b))
        old = self.road_factor.get(key, 1.0)
        self.road_factor[key] = 0.3 * old + 0.7 * factor


@dataclass
class RoadBelief:
    a: float = 1.0       # congested / closed
    b: float = 4.0

    @property
    def p_bad(self) -> float:
        return self.a / (self.a + self.b)

    def observe(self, bad: bool) -> None:
        if bad:
            self.a += 2.0
        else:
            self.b += 1.0


class WorldBelief:
    """All world beliefs for one drive."""

    def __init__(self, env: Any, reliability_prior: float = 4.0):
        self.env = env
        self.stations: dict[str, StationBelief] = {}
        for s in env.state["stations"]:
            # live status is strong evidence, but stations can change before we arrive
            self.stations[s["id"]] = (StationBelief(reliability_prior + 1, 0.5) if s["available"]
                                      else StationBelief(0.5, reliability_prior + 1))
        self.battery = BatteryBelief()
        d = env.driving
        sd = 0.15 + (0.1 if d.get("weather") == "rain" else 0.0) + (0.05 if d.get("traffic") == "heavy" else 0.0)
        self.travel = TravelTimeBelief(TRAFFIC_MEAN.get(d.get("traffic"), 1.2), sd)
        prior_bad = 1.0 + (1.0 if d.get("weather") == "rain" else 0.0) + (1.0 if d.get("traffic") == "heavy" else 0.0)
        self.roads: dict[frozenset, RoadBelief] = {frozenset((r["from"], r["to"])): RoadBelief(prior_bad, 4.0)
                                                   for r in env.state["roads"]}
        self.log: list[str] = []

    # ------------------------------------------------------------ observations
    def observe_station(self, station_id: str, available: bool) -> None:
        sb = self.stations.setdefault(station_id, StationBelief(1, 1))
        sb.observe(available, 3.0)
        self.log.append(f"station {station_id} {'available' if available else 'unavailable'} -> "
                        f"P(available)={sb.p_available:.2f}")

    def observe_drive(self, expected_kwh: float, actual_kwh: float) -> None:
        self.battery.observe(expected_kwh, actual_kwh)
        self.log.append(f"energy used {actual_kwh:.2f} kWh vs {expected_kwh:.2f} expected -> "
                        f"consumption factor {self.battery.mean:.2f} +/- {self.battery.sd:.2f}")

    def observe_traffic(self, traffic: dict[str, Any]) -> None:
        seen = set()
        for inc in traffic.get("incidents", []):
            key = frozenset((inc["from"], inc["to"]))
            seen.add(key)
            self.roads.setdefault(key, RoadBelief()).observe(True)
            self.travel.observe_delay(inc["from"], inc["to"], 50.0 if inc.get("closed") else inc["delay_factor"])
        for key, rb in self.roads.items():
            if key not in seen:
                rb.observe(False)
        self.log.append(f"live traffic: {len(seen)} incident(s)")

    def observe_closed(self, a: str, b: str) -> None:
        self.roads.setdefault(frozenset((a, b)), RoadBelief()).observe(True)
        self.travel.observe_delay(a, b, 50.0)
        self.log.append(f"road {a}-{b} closed")

    # ------------------------------------------------------------ queries
    def availability(self) -> dict[str, float]:
        return {sid: round(b.p_available, 3) for sid, b in self.stations.items()}

    def cautious_consumption(self, q: float = 0.9) -> float:
        return round(max(1.0, self.battery.quantile(q)), 3)

    def p_reach(self, model_energy_kwh: float, reserve_pct: float = 10.0) -> float:
        v = self.env.vehicle
        usable = v["battery_capacity_kwh"] * max(0.0, v["battery_pct"] - reserve_pct) / 100.0
        return self.battery.p_reach(model_energy_kwh, usable)

    def route_legs(self, route: dict[str, Any] | None) -> list[tuple[str, str, float]]:
        if not route:
            return []
        out = []
        path = route["path"]
        for a, b in zip(path, path[1:]):
            road = next((r for r in self.env.neighbours(a) if r["to"] == b), None)
            if road is not None:
                out.append((a, b, self.env.edge_time_min(road)))
        return out

    def summary(self) -> dict[str, Any]:
        nav = self.env.navigation
        out: dict[str, Any] = {
            "station_availability": self.availability(),
            "consumption_factor": {"mean": round(self.battery.mean, 3), "sd": round(self.battery.sd, 3),
                                   "observations": self.battery.n},
            "congested_roads": sorted("-".join(sorted(k)) for k, r in self.roads.items() if r.p_bad > 0.5),
        }
        if nav.get("active") and nav.get("route"):
            legs = self.route_legs(nav["route"])
            mean, sd = self.travel.route_time(legs)
            out["route_time_min"] = {"mean": round(mean, 1), "sd": round(sd, 1), "p90": round(mean + 1.28 * sd, 1)}
            out["p_reach_destination"] = round(self.p_reach(nav["route"]["energy_kwh"]), 3)
        return out
