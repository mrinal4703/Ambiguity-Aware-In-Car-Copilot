"""EV charging as a CSP (module 6, owner: Prasanna).

Variables
    station   – a charging station id
    target    – charge target in % (50..100)
    route     – route preference for both legs (fastest / shortest / eco / no_toll)

Hard constraints
    tools_available    – the car can search stations and navigate
    connector          – station supports the car's connector
    available          – station is currently available
    reach_station      – leg 1 energy <= battery - reserve
    charge_useful      – target is above the state of charge on arrival
    reach_destination  – leg 2 energy <= charged energy - reserve
    deadline           – leg1 + charging + leg2 time <= time available
    no_toll            – (only if required) neither leg uses a toll road

Soft preferences (ranking among feasible solutions): total time, tolls,
preferred network, price.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts import FeasibilityResult, RouteOption
from module_5_search import RouteSolver

from .csp import CSP, SearchStats

RESERVE_PCT = 10.0
TARGETS = [50, 60, 70, 80, 90, 100]
PREFS = ["fastest", "shortest", "eco", "no_toll"]
CHARGER_EFFICIENCY = 0.9
DC_TAPER_ABOVE_PCT = 80.0       # DC fast chargers slow to half power above 80 %
REQUIRED_FEATURES = ("charging_search", "navigation")

CONSTRAINT_TEXT = {
    "tools_available": "the car cannot search charging stations or navigate",
    "connector": "connector not compatible with the car",
    "available": "station is currently unavailable",
    "reach_station": "not enough battery to reach the station with the reserve",
    "charge_useful": "charge target is not above the arrival charge",
    "reach_destination": "cannot reach the destination after charging",
    "deadline": "would miss the deadline",
    "no_toll": "route uses a toll road",
    "excluded": "station was ruled out earlier (failed during execution)",
}


@dataclass
class ChargingProblem:
    origin: str
    destination: str | None
    battery_pct: float
    capacity_kwh: float
    connector: str
    stations: list[dict[str, Any]]
    deadline_min: float | None = None          # minutes available from now
    reserve_pct: float = RESERVE_PCT
    avoid_tolls: bool = False
    preferred_network: str | None = None
    features: tuple[str, ...] = REQUIRED_FEATURES
    desired_pct: int = 80                      # soft: preferred charge target
    exclude: tuple[str, ...] = ()              # stations ruled out (e.g. failed during execution)
    targets: list[int] = field(default_factory=lambda: list(TARGETS))
    prefs: list[str] = field(default_factory=lambda: list(PREFS))

    @property
    def battery_kwh(self) -> float:
        return self.capacity_kwh * self.battery_pct / 100.0

    @property
    def reserve_kwh(self) -> float:
        return self.capacity_kwh * self.reserve_pct / 100.0

    @classmethod
    def from_env(cls, env: Any, destination: str | None = None, deadline_min: float | None = None,
                 **kw: Any) -> "ChargingProblem":
        v = env.vehicle
        return cls(origin=v["location"], destination=env.resolve_node(destination) if destination else None,
                   battery_pct=v["battery_pct"], capacity_kwh=v["battery_capacity_kwh"], connector=v["connector"],
                   stations=[dict(s) for s in env.state["stations"]], deadline_min=deadline_min,
                   features=tuple(v["features"]), **kw)


@dataclass
class ChargingSolution:
    station: dict[str, Any]
    target_pct: int
    preference: str
    option: RouteOption
    charge_min: float
    total_min: float
    arrival_pct: float
    final_pct: float
    score: float

    def summary(self) -> str:
        return (f"Charge at {self.station['name']} to {self.target_pct}% ({self.charge_min:.0f} min), "
                f"total {self.total_min:.0f} min, arrive with {self.final_pct:.0f}%")


@dataclass
class ChargingResult:
    feasible: bool
    best: ChargingSolution | None
    solutions: list[ChargingSolution]
    station_results: list[FeasibilityResult]
    explanation: str
    stats: SearchStats

    def ranked_options(self, k: int = 3) -> list[ChargingSolution]:
        """Best solution per station, best first."""
        seen, out = set(), []
        for s in self.solutions:
            if s.station["id"] not in seen:
                seen.add(s.station["id"])
                out.append(s)
        return out[:k]


def charge_minutes(station: dict[str, Any], capacity_kwh: float, from_pct: float, to_pct: float) -> float:
    if to_pct <= from_pct:
        return 0.0
    p = station["power_kw"]
    dc = p > 22
    def seg(a: float, b: float, power: float) -> float:
        return max(0.0, b - a) / 100.0 * capacity_kwh / (power * CHARGER_EFFICIENCY) * 60.0
    if not dc:
        return seg(from_pct, to_pct, p)
    t = seg(from_pct, min(to_pct, DC_TAPER_ABOVE_PCT), p)
    t += seg(max(from_pct, DC_TAPER_ABOVE_PCT), to_pct, p / 2)
    return t


class ChargingPlanner:
    def __init__(self, solver: RouteSolver):
        self.solver = solver
        self._legs: dict[tuple[str, str, str], Any] = {}

    @classmethod
    def from_env(cls, env: Any) -> "ChargingPlanner":
        return cls(RouteSolver.from_env(env))

    def _leg(self, a: str, b: str | None, pref: str):
        if b is None or a == b:
            return None
        key = (a, b, pref)
        if key not in self._legs:
            self._legs[key] = self.solver.route(a, b, preference=pref)
        return self._legs[key]

    @staticmethod
    def _m(leg, attr: str) -> float:
        return getattr(leg, attr) if leg is not None else 0.0

    def build_csp(self, pb: ChargingProblem) -> CSP:
        st = {s["id"]: s for s in pb.stations}
        csp = CSP(["station", "target", "route"],
                  {"station": list(st), "target": list(pb.targets), "route": list(pb.prefs)})
        leg1 = lambda s, r: self._leg(pb.origin, st[s]["node"], r)
        leg2 = lambda s, r: self._leg(st[s]["node"], pb.destination, r)
        def routable(s: str, r: str) -> bool:
            if pb.origin != st[s]["node"] and leg1(s, r) is None:
                return False
            return pb.destination is None or st[s]["node"] == pb.destination or leg2(s, r) is not None
        arrival = lambda s, r: pb.battery_pct - self._m(leg1(s, r), "energy_kwh") / pb.capacity_kwh * 100

        csp.add("tools_available", ("station",), lambda s: all(f in pb.features for f in REQUIRED_FEATURES))
        csp.add("connector", ("station",), lambda s: pb.connector in st[s]["connectors"])
        csp.add("available", ("station",), lambda s: bool(st[s]["available"]))
        if pb.exclude:
            csp.add("excluded", ("station",), lambda s: s not in pb.exclude)
        csp.add("reach_station", ("station", "route"),
                lambda s, r: routable(s, r) and arrival(s, r) >= pb.reserve_pct)
        csp.add("charge_useful", ("station", "target", "route"), lambda s, t, r: t > arrival(s, r))
        csp.add("reach_destination", ("station", "target", "route"),
                lambda s, t, r: t - self._m(leg2(s, r), "energy_kwh") / pb.capacity_kwh * 100 >= pb.reserve_pct)
        if pb.deadline_min is not None:
            csp.add("deadline", ("station", "target", "route"),
                    lambda s, t, r: self._total(pb, st[s], t, r) <= pb.deadline_min)
        if pb.avoid_tolls:
            csp.add("no_toll", ("station", "route"),
                    lambda s, r: not (self._m(leg1(s, r), "toll") or self._m(leg2(s, r), "toll")))
        return csp

    def _total(self, pb: ChargingProblem, station: dict[str, Any], t: int, r: str) -> float:
        l1, l2 = self._leg(pb.origin, station["node"], r), self._leg(station["node"], pb.destination, r)
        arr = pb.battery_pct - self._m(l1, "energy_kwh") / pb.capacity_kwh * 100
        return self._m(l1, "time_min") + charge_minutes(station, pb.capacity_kwh, arr, t) + self._m(l2, "time_min")

    def _score(self, pb: ChargingProblem, s: dict[str, Any], t: int, r: str) -> float:
        l1, l2 = self._leg(pb.origin, s["node"], r), self._leg(s["node"], pb.destination, r)
        score = 0.3 * self._total(pb, s, t, r)
        score += 3.0 if (self._m(l1, "toll") or self._m(l2, "toll")) else 0.0
        if pb.preferred_network and s.get("network") != pb.preferred_network:
            score += 6.0
        score += 0.02 * s.get("price_per_kwh", 0) * (t / 100 * pb.capacity_kwh)
        score += 0.5 * abs(t - pb.desired_pct)
        return score

    def solve(self, pb: ChargingProblem, forward_checking: bool = True, mrv: bool = True) -> ChargingResult:
        csp = self.build_csp(pb)
        sols, stats, _ = csp.solve(all_solutions=True, forward_checking=forward_checking, mrv=mrv)
        st = {s["id"]: s for s in pb.stations}
        out = [self._solution(pb, st[a["station"]], a["target"], a["route"]) for a in sols]
        out.sort(key=lambda s: s.score)
        per_station = self.explain_stations(pb, csp, {s.station["id"] for s in out})
        if out:
            expl = out[0].summary()
        else:
            reasons = "; ".join(f"{r.route_id.removeprefix('via_')}: {r.notes}" for r in per_station)
            expl = "No feasible charging plan. " + reasons
        return ChargingResult(bool(out), out[0] if out else None, out, per_station, expl, stats)

    def _solution(self, pb: ChargingProblem, s: dict[str, Any], t: int, r: str) -> ChargingSolution:
        l1, l2 = self._leg(pb.origin, s["node"], r), self._leg(s["node"], pb.destination, r)
        arr = pb.battery_pct - self._m(l1, "energy_kwh") / pb.capacity_kwh * 100
        cm = charge_minutes(s, pb.capacity_kwh, arr, t)
        final = t - self._m(l2, "energy_kwh") / pb.capacity_kwh * 100
        path = (l1.path if l1 else [pb.origin]) + (l2.path[1:] if l2 else [])
        opt = RouteOption(
            id=f"via_{s['id']}", waypoints=[s["id"]] + ([pb.destination] if pb.destination else []),
            distance_km=round(self._m(l1, "distance_km") + self._m(l2, "distance_km"), 2),
            time_min=round(self._m(l1, "time_min") + self._m(l2, "time_min"), 1),
            energy_kwh=round(self._m(l1, "energy_kwh") + self._m(l2, "energy_kwh"), 2),
            cost=round(self._score(pb, s, t, r), 2),
            metadata={"station_id": s["id"], "station_name": s["name"], "target_pct": t, "preference": r,
                      "charge_min": round(cm, 1), "path": path, "arrival_pct": round(arr, 1),
                      "final_pct": round(final, 1)})
        return ChargingSolution(s, t, r, opt, round(cm, 1), round(self._total(pb, s, t, r), 1), round(arr, 1),
                                round(final, 1), round(self._score(pb, s, t, r), 2))

    def explain_stations(self, pb: ChargingProblem, csp: CSP, feasible_ids: set[str]) -> list[FeasibilityResult]:
        """For each infeasible station, report the constraints that rule out every (target, route)."""
        out = []
        for s in pb.stations:
            sid = s["id"]
            if sid in feasible_ids:
                out.append(FeasibilityResult(route_id=f"via_{sid}", feasible=True, notes="feasible"))
                continue
            unary = [c.name for c in csp.constraints if c.scope == ("station",) and not c.predicate(sid)]
            if unary:
                v = unary
            else:
                # report what blocks the most promising combination, so "would miss the deadline" is not
                # drowned out by (route, target) combos that fail for unrelated reasons
                order = list(CONSTRAINT_TEXT)
                combos = [sorted(csp.violations({"station": sid, "target": t, "route": r}),
                                 key=lambda n: order.index(n) if n in order else len(order))
                          for r in pb.prefs for t in pb.targets]
                combos = [c for c in combos if c]
                # keep only combos that satisfy each constraint (in CONSTRAINT_TEXT order) whenever some combo can
                for name in order:
                    sat = [c for c in combos if name not in c]
                    if sat:
                        combos = sat
                v = min(combos, key=len) if combos else []
            notes = ", ".join(CONSTRAINT_TEXT.get(n, n) for n in v[:2])
            out.append(FeasibilityResult(route_id=f"via_{sid}", feasible=False, violated_constraints=v, notes=notes))
        return out


def check_direct(env: Any, destination: str, deadline_min: float | None = None,
                 reserve_pct: float = RESERVE_PCT, solver: RouteSolver | None = None) -> FeasibilityResult:
    """Can we drive straight to `destination` without charging?"""
    solver = solver or RouteSolver.from_env(env)
    d = env.resolve_node(destination)
    v = env.vehicle
    r = solver.route(v["location"], d) if d else None
    if r is None:
        return FeasibilityResult(route_id="direct", feasible=False, violated_constraints=["route_exists"],
                                 notes=f"no route to {destination}")
    left = v["battery_pct"] - r.energy_kwh / v["battery_capacity_kwh"] * 100
    viol = []
    if left < reserve_pct:
        viol.append("reach_destination")
    if deadline_min is not None and r.time_min > deadline_min:
        viol.append("deadline")
    notes = f"{r.distance_km:.1f} km, {r.time_min:.0f} min, arrive with {left:.0f}% battery"
    return FeasibilityResult(route_id="direct", feasible=not viol, violated_constraints=viol, notes=notes)
