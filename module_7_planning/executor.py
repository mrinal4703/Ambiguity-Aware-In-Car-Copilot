"""Plan execution with precondition checks, outcome verification and replanning (module 7).

    ex = Executor(env, gate=my_safety_gate)
    report = ex.start("find_charging", {"near": "@current_route"})
    if report.status == "awaiting_confirmation":
        report = ex.resume(report, confirmed=True)

`gate(step, params, env, confirmed) -> SafetyVerdict | None` is called before every
tool step (module 9 plugs in here). ALLOW / None runs the step; CONFIRM pauses until
`resume`; DEFER pauses; BLOCK stops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from contracts import Plan, PlanStep, SafetyVerdict, Verdict
from module_1_simulator.world import haversine_km
from module_6_csp import ChargingPlanner, ChargingProblem, check_direct

from .actions import (ABORT, INTERNAL_ACTIONS, REPLAN_EXCLUDE_STATION, REPLAN_WITH_CHARGING, RETRY,
                      UnsupportedGoal, initial_facts)
from .planner import NoPlan, Planner

Gate = Callable[[PlanStep, dict[str, Any], Any, bool], SafetyVerdict | None]


@dataclass
class StepOutcome:
    step_id: str
    action: str
    params: dict[str, Any]
    ok: bool
    data: Any = None
    error: str | None = None
    verified: bool = False
    note: str = ""


@dataclass
class ExecutionReport:
    goal: str
    params: dict[str, Any]
    context: dict[str, Any]
    status: str = "running"         # completed | failed | blocked | awaiting_confirmation | deferred | cancelled
    plan: Plan | None = None
    plans: list[Plan] = field(default_factory=list)
    outcomes: list[StepOutcome] = field(default_factory=list)
    blackboard: dict[str, Any] = field(default_factory=dict)
    facts: frozenset[str] = frozenset()
    done: set[str] = field(default_factory=set)
    confirmed: set[str] = field(default_factory=set)
    pending: PlanStep | None = None
    pending_params: dict[str, Any] = field(default_factory=dict)
    verdict: SafetyVerdict | None = None
    replans: int = 0
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"

    def tool_calls(self) -> list[StepOutcome]:
        return [o for o in self.outcomes if o.action not in INTERNAL_ACTIONS]


class StepFailed(Exception):
    pass


class Executor:
    def __init__(self, env: Any, planner: Planner | None = None, gate: Gate | None = None,
                 max_replans: int = 2, max_retries: int = 1):
        self.env = env
        self.planner = planner or Planner()
        self.gate = gate
        self.max_replans = max_replans
        self.max_retries = max_retries

    # ----------------------------------------------------------------- public
    def start(self, goal: str, params: dict[str, Any], context: dict[str, Any] | None = None,
              plan: Plan | None = None) -> ExecutionReport:
        rep = ExecutionReport(goal=goal, params=dict(params), context=dict(context or {}))
        rep.facts = initial_facts(self.env)
        try:
            rep.plan = plan or self.planner.plan(goal, params, self.env, rep.context, rep.facts)
        except UnsupportedGoal:
            rep.status, rep.message = "failed", f"unsupported goal '{goal}'"
            return rep
        except NoPlan as e:
            rep.status, rep.message = "failed", str(e)
            return rep
        rep.plans.append(rep.plan)
        return self._run(rep)

    def resume(self, rep: ExecutionReport, confirmed: bool = True) -> ExecutionReport:
        if rep.pending is None:
            return rep
        if not confirmed:
            rep.status, rep.message = "cancelled", f"cancelled {rep.pending.action}"
            rep.pending = None
            return rep
        rep.confirmed.add(rep.pending.id)
        rep.pending, rep.status = None, "running"
        return self._run(rep)

    # -------------------------------------------------------------- main loop
    def _run(self, rep: ExecutionReport) -> ExecutionReport:
        while True:
            step = next((s for s in rep.plan.steps if s.id not in rep.done), None)
            if step is None:
                rep.status = "completed"
                rep.message = rep.message or "done"
                return rep
            missing = [f for f in step.preconditions if f not in rep.facts]
            if missing:
                rep.status, rep.message = "failed", f"{step.action}: preconditions not met {missing}"
                return rep
            try:
                params = self._resolve(step.params, rep.blackboard)
            except KeyError as e:
                rep.status, rep.message = "failed", f"{step.action}: missing input {e}"
                return rep
            if step.action not in INTERNAL_ACTIONS and self.gate is not None:
                v = self.gate(step, params, self.env, step.id in rep.confirmed)
                if v is not None and v.verdict != Verdict.ALLOW:
                    rep.verdict = v
                    if v.verdict == Verdict.BLOCK:
                        rep.status, rep.message = "blocked", v.reason
                        return rep
                    rep.pending, rep.pending_params = step, params
                    rep.status = "awaiting_confirmation" if v.verdict == Verdict.CONFIRM else "deferred"
                    rep.message = v.reason
                    return rep
            outcome = self._attempt(step, params, rep)
            rep.outcomes.append(outcome)
            if outcome.ok and outcome.verified:
                rep.done.add(step.id)
                rep.blackboard[step.action] = outcome.data
                rep.facts = (rep.facts - self._deletes(step)) | frozenset(step.effects)
                continue
            if not self._recover(step, params, outcome, rep):
                return rep

    def _attempt(self, step: PlanStep, params: dict[str, Any], rep: ExecutionReport) -> StepOutcome:
        tries = 1 + (self.max_retries if step.recovery == RETRY else 0)
        out = None
        for _ in range(tries):
            out = self._do(step, params, rep)
            if out.ok and out.verified:
                break
        return out

    def _do(self, step: PlanStep, params: dict[str, Any], rep: ExecutionReport) -> StepOutcome:
        if step.action in INTERNAL_ACTIONS:
            try:
                data = getattr(self, f"_i_{step.action}")(params, rep)
                return StepOutcome(step.id, step.action, params, True, data, verified=True)
            except StepFailed as e:
                return StepOutcome(step.id, step.action, params, False, error=str(e))
        res = self.env.call(step.action, **{k: v for k, v in params.items() if v is not None})
        if not res.ok:
            return StepOutcome(step.id, step.action, params, False, res.data, res.error)
        ok, note = self._verify(step.action, params, res.data)
        return StepOutcome(step.id, step.action, params, True, res.data, None if ok else note, ok, note)

    # -------------------------------------------------------------- recovery
    def _recover(self, step: PlanStep, params: dict[str, Any], out: StepOutcome, rep: ExecutionReport) -> bool:
        err = out.error or "verification failed"
        if rep.replans >= self.max_replans or step.recovery in (ABORT, RETRY, None):
            rep.status, rep.message = "failed", f"{step.action} failed: {err}"
            return False
        if step.recovery == REPLAN_EXCLUDE_STATION:
            sid = (rep.blackboard.get("choose_charging_station") or {}).get("station_id")
            rep.context["exclude_stations"] = tuple({*rep.context.get("exclude_stations", ()), sid})
            rep.facts = rep.facts - {"station_chosen", "station_available"}
            goal, params2 = rep.goal, rep.params
        elif step.recovery == REPLAN_WITH_CHARGING:
            goal, params2 = "navigate_with_charging", {"destination": params.get("destination")}
            rep.goal, rep.params = goal, params2
        else:
            rep.status, rep.message = "failed", f"{step.action} failed: {err}"
            return False
        rep.replans += 1
        try:
            new = self.planner.plan(goal, params2, self.env, rep.context, rep.facts)
        except (NoPlan, UnsupportedGoal) as e:
            rep.status, rep.message = "failed", f"{step.action} failed ({err}) and replanning failed: {e}"
            return False
        # give new steps fresh ids so outcomes stay unambiguous
        prefix = f"r{rep.replans}_"
        idmap = {s.id: prefix + s.id for s in new.steps}
        new = Plan(goal=new.goal, steps=[s.model_copy(update={"id": idmap[s.id],
                                                              "depends_on": [idmap[d] for d in s.depends_on]})
                                         for s in new.steps])
        rep.plan = new
        rep.plans.append(new)
        rep.message = f"replanned after {step.action} failed: {err}"
        return True

    @staticmethod
    def _deletes(step: PlanStep) -> frozenset[str]:
        return frozenset({"not_navigating"}) if step.action in ("set_navigation",) else frozenset()

    # ------------------------------------------------------------ parameters
    @staticmethod
    def _resolve(params: dict[str, Any], bb: dict[str, Any]) -> dict[str, Any]:
        def r(v: Any) -> Any:
            if isinstance(v, list):
                return [r(x) for x in v]
            if isinstance(v, str) and v.startswith("$"):
                src, key = v[1:].split(".", 1)
                if src not in bb or key not in bb[src]:
                    raise KeyError(v)
                return bb[src][key]
            return v
        return {k: r(v) for k, v in params.items()}

    # ------------------------------------------------------------ verification
    def _verify(self, tool: str, params: dict[str, Any], data: Any) -> tuple[bool, str]:
        env = self.env
        if tool == "get_station_status":
            return (bool(data.get("available")), "" if data.get("available") else
                    f"station {data.get('id')} is unavailable")
        if tool == "set_navigation":
            ok = env.navigation["active"] and env.navigation["destination"] == env.resolve_node(params["destination"])
            return ok, "" if ok else "navigation not active"
        if tool == "add_waypoint":
            ok = params["waypoint"] in env.navigation["waypoints"]
            return ok, "" if ok else "waypoint missing from route"
        if tool == "send_message":
            ok = bool(env.state["messages_sent"]) and env.state["messages_sent"][-1]["to"] == params["contact_id"]
            return ok, "" if ok else "message not recorded"
        if tool == "make_call":
            ok = bool(env.state["calls"]) and env.state["calls"][-1]["to"] == params["contact_id"]
            return ok, "" if ok else "call not started"
        if tool == "control_ac":
            ac = env.vehicle["ac"]
            ok = ("temperature_c" not in params or ac["temperature_c"] == float(params["temperature_c"]))
            ok = ok and ac["on"] == (True if params.get("on") is None else bool(params["on"]))
            return ok, "" if ok else "AC state differs from request"
        if tool == "control_windows":
            ws = env.vehicle["windows"]
            keys = list(ws) if params.get("window", "all") == "all" else [params["window"]]
            ok = all(ws[k] == int(params["position"]) for k in keys)
            return ok, "" if ok else "window position differs"
        if tool == "add_reminder":
            ok = bool(env.state["reminders"]) and env.state["reminders"][-1]["text"] == params["text"]
            return ok, "" if ok else "reminder not stored"
        return True, ""

    # ------------------------------------------------------- internal actions
    def _i_check_range(self, p: dict[str, Any], rep: ExecutionReport) -> dict[str, Any]:
        f = check_direct(self.env, p["destination"], rep.context.get("deadline_min"))
        if "route_exists" in f.violated_constraints:
            raise StepFailed(f.notes)
        if "reach_destination" in f.violated_constraints:
            raise StepFailed(f"not enough charge to reach {p['destination']} directly ({f.notes})")
        return {"feasible": True, "notes": f.notes}

    def _i_choose_charging_station(self, p: dict[str, Any], rep: ExecutionReport) -> dict[str, Any]:
        found = rep.blackboard.get("search_charging_stations")
        ids = {s["id"] for s in found} if found else None
        pb = ChargingProblem.from_env(self.env, p.get("destination"), p.get("deadline_min"),
                                      avoid_tolls=bool(p.get("avoid_tolls")),
                                      exclude=tuple(set(p.get("exclude") or ()) |
                                                    set(rep.context.get("exclude_stations", ()))))
        if ids is not None:
            pb.stations = [s for s in pb.stations if s["id"] in ids]
        res = ChargingPlanner.from_env(self.env).solve(pb)
        rep.blackboard["charging_result"] = res
        if not res.feasible:
            raise StepFailed(res.explanation)
        b = res.best
        return {"station_id": b.station["id"], "station_name": b.station["name"], "node": b.station["node"],
                "target_pct": b.target_pct, "charge_min": b.charge_min, "total_min": b.total_min,
                "final_pct": b.final_pct, "summary": b.summary(),
                "alternatives": [s.summary() for s in res.ranked_options(3)[1:]]}

    def _i_choose_poi(self, p: dict[str, Any], rep: ExecutionReport) -> dict[str, Any]:
        pois = rep.blackboard.get("search_poi") or []
        if not pois:
            raise StepFailed(f"no {p.get('category', 'place')} found nearby")
        locs = self.env.state["locations"]
        route = (self.env.navigation.get("route") or {}).get("path") or [self.env.vehicle["location"]]
        def detour(poi: dict[str, Any]) -> float:
            return min(haversine_km(locs[poi["node"]]["coords"], locs[n]["coords"]) for n in route)
        best = min(pois, key=detour)
        return {"poi_id": best["id"], "name": best["name"], "node": best["node"],
                "detour_km": round(detour(best), 2)}

    def _i_resolve_contact(self, p: dict[str, Any], rep: ExecutionReport) -> dict[str, Any]:
        r = p.get("recipient")
        if not r or str(r).startswith("@"):
            raise StepFailed("recipient is not resolved")
        c = self.env.contact(r)
        if c is None:
            q = str(r).lower()
            matches = [x for x in self.env.state["contacts"] if q in x["name"].lower() or q == x["relation"]]
            if len(matches) != 1:
                raise StepFailed(f"recipient '{r}' matches {len(matches)} contacts")
            c = matches[0]
        return {"contact_id": c["id"], "name": c["name"], "allow_messages": c.get("allow_messages", True)}

    def _i_compose_answer(self, p: dict[str, Any], rep: ExecutionReport) -> dict[str, Any]:
        return {"text": p.get("text", "")}
