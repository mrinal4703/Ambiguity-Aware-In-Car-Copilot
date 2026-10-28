"""The orchestrator (module 10).

    utterance -> NLU (2) -> beliefs over intent and world (3) -> EVPI / RL decision (4 / 8)
              -> plan with search + CSP + STRIPS planner (5, 6, 7)
              -> safety gate (9) -> execute + verify (1, 7, 9) -> response

While driving (`drive`, `event`) the trip monitor (7) watches the route against the
world beliefs (3) and replans when a road closes, a charging stop goes offline or the
battery drains faster than expected.

The agent is multi-turn: it can be waiting for a clarification answer or for a
confirmation. Every reply is built from verified tool results only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from contracts import BeliefState, Candidate, ClarificationHistory, DecisionKind, SafetyVerdict, Verdict
from module_1_simulator.environment import CarEnvironment, hhmm
from module_1_simulator.environment import minutes as to_minutes
from module_2_nlu import RuleBasedParser
from module_2_nlu.llm_parser import LLMParser, make_parser
from module_2_nlu.rule_parser import classify_confirmation
from module_3_uncertainty import BeliefBuilder, BeliefBundle, ContextResolver, PreferenceModel, WorldBelief, goal_of
from module_4_evpi import EVPIClarifier, match_answer, score_all, make_question, answer_options
from module_4_evpi.clarifier import ClarifierConfig
from module_7_planning import Executor, ExecutionReport, TripMonitor
from module_9_safety import SafetyContext, SafetyPolicy, check_request
from module_9_safety.policy_engine import SafetyConfig

from .config import AgentConfig

INFO_GOALS = {"info_calendar", "info_vehicle", "info_eta", "info_traffic", "chat"}
CHARGING_GOALS = {"find_charging", "navigate_with_charging"}
EMERGENCY_RESERVE_PCT = 1.0


@dataclass
class Turn:
    user: str
    reply: str
    kind: str = "answer"            # answer | question | confirm | done | blocked | deferred | failed | refused
    decision: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    plan: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    verdict: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class _Pending:
    kind: str                       # "clarify" | "confirm"
    bundle: BeliefBundle | None = None
    belief: BeliefState | None = None
    history: ClarificationHistory | None = None
    decision: Any = None
    executor: Executor | None = None
    report: ExecutionReport | None = None
    task_meta: dict[str, Any] = field(default_factory=dict)


class CopilotAgent:
    def __init__(self, env: CarEnvironment | None = None, config: AgentConfig | None = None,
                 parser: Any = None, rl_agent: Any = None):
        self.env = env or CarEnvironment()
        self.config = config or AgentConfig()
        self.parser = parser or self._make_parser()
        self.clarifier = EVPIClarifier(ClarifierConfig(budget=self.config.question_budget))
        conf_nav = self.config.proactivity == "low"
        self.safety = SafetyPolicy(SafetyConfig(confirm_navigation_when_inferred=self.config.proactivity != "high"))
        self._confirm_all_nav = conf_nav
        self.rl_agent = rl_agent
        if self.config.policy == "rl" and self.rl_agent is None:
            from module_8_rl.evaluate import train_agent
            self.rl_agent = train_agent()
        self.world = WorldBelief(self.env)          # module 3: beliefs over stations, battery, travel time
        self.prefs = PreferenceModel()              # module 3: learned from the driver's past choices
        self.monitor = TripMonitor(self.env, self.world)
        self.responder = None
        if self.config.responder == "llm":
            from module_2_nlu.responder import GroundedResponder
            self.responder = GroundedResponder()
        self.pending: _Pending | None = None
        self.queue: list[BeliefBundle] = []
        self.history: list[Turn] = []
        self.dialog: list[dict[str, str]] = []
        self.stats = {"questions": 0, "context_lookups": 0, "blocked": 0, "deferred": 0, "fabricated": 0,
                      "confirmations": 0, "replans": 0}

    def _make_parser(self):
        p = self.config.parser
        if p == "rules":
            return RuleBasedParser()
        if p == "llm":
            return LLMParser()
        return make_parser()

    # ================================================================ public
    def reset(self, env: CarEnvironment | None = None) -> None:
        self.__init__(env or CarEnvironment(), self.config, self.parser, self.rl_agent)

    def handle(self, utterance: str) -> Turn:
        self.dialog.append({"role": "user", "content": utterance})
        turn = self._handle(utterance)
        if self.responder is not None and turn.kind not in ("question", "confirm"):
            turn.reply = self.responder.rephrase(turn.reply, turn.tool_calls)
        self.history.append(turn)
        self.dialog.append({"role": "assistant", "content": turn.reply})
        return turn

    def drive(self, minutes: float) -> Turn:
        """Advance the simulation; update world beliefs; replan if the trip is at risk."""
        res = self.env.drive(minutes)
        if res.get("expected_kwh"):
            self.world.observe_drive(res["expected_kwh"], res["actual_kwh"])
        note = (f"Drove {res['moved_km']:.1f} km. " if res["moved_km"] else "") + \
            f"Battery {self.env.vehicle['battery_pct']:.0f}%."
        for ev in res.get("events", []):
            if isinstance(ev, str) and not ev.startswith("road "):   # closures are explained by the monitor
                note += f" {ev[0].upper() + ev[1:]}."
        return self._record(f"[drive {minutes:g} min]", self.check_trip(note))

    def event(self, kind: str, **kw: Any) -> Turn:
        """External change: road_closed(a, b) | station_offline(station) | drain(factor) | traffic(a, b, factor)."""
        env = self.env
        self._check_event(kind, kw)
        if kind == "road_closed":
            env.close_road(kw["a"], kw["b"])
            self.world.observe_closed(kw["a"], kw["b"])
            note = ""
            if not env.route_blocked():
                note = f"Road {env.location_name(kw['a'])} - {env.location_name(kw['b'])} closed; it is not on your route."
        elif kind == "station_offline":
            env.set_station_availability(kw["station"], False)
            self.world.observe_station(kw["station"], False)
            note = ""
            on_trip = kw["station"] in env.navigation.get("waypoints", []) or kw["station"] == self.monitor.target_station
            if not on_trip:
                note = f"{env.station(kw['station'])['name']} went offline; it is not on your trip."
        elif kind == "drain":
            env.set_actual_consumption(float(kw["factor"]))
            note = "Battery drain changed."
        elif kind == "traffic":
            env.set_road_delay(kw["a"], kw["b"], float(kw["factor"]))
            note = "Traffic changed."
        else:
            raise ValueError(f"unknown event {kind}")
        return self._record(f"[event {kind}]", self.check_trip(note))

    _EVENT_ARGS = {"road_closed": ("a", "b"), "station_offline": ("station",), "drain": ("factor",),
                   "traffic": ("a", "b", "factor")}

    def _check_event(self, kind: str, kw: dict[str, Any]) -> None:
        """Reject malformed events with a clear message before anything changes."""
        if kind not in self._EVENT_ARGS:
            raise ValueError(f"unknown event '{kind}' (use one of: {', '.join(self._EVENT_ARGS)})")
        missing = [k for k in self._EVENT_ARGS[kind] if kw.get(k) is None]
        if missing:
            raise ValueError(f"event '{kind}' needs: {', '.join(missing)}")
        if "station" in kw and self.env.station(kw["station"]) is None:
            raise ValueError(f"unknown station '{kw['station']}'")
        if "a" in kw and not any(r["to"] == kw["b"] for r in self.env.neighbours(kw["a"])):
            raise ValueError(f"no open road between '{kw['a']}' and '{kw['b']}'")
        if "factor" in kw and not 0.1 <= float(kw["factor"]) <= 10:
            raise ValueError("factor must be between 0.1 and 10")

    def _record(self, user: str, turn: Turn) -> Turn:
        turn.user = user
        self.history.append(turn)
        self.dialog.append({"role": "assistant", "content": turn.reply})
        return turn

    def check_trip(self, note: str = "") -> Turn:
        """Run the trip monitor; repair the plan if needed."""
        if not self.config.use_planning or self.pending is not None:
            return Turn("", note.strip(), "answer")
        issues = self.monitor.check()
        if not issues:
            return Turn("", note.strip(), "answer")
        issue = issues[0]
        self.stats["replans"] += 1
        if issue.goal is None:
            r = self.monitor.reroute()
            if r["ok"]:
                rt = r["route"]
                reply = (f"{note} {issue.detail[0].upper() + issue.detail[1:]}, so I rerouted: "
                         f"{rt['distance_km']:.1f} km, about {rt['time_min']:.0f} min.")
                return Turn("", reply.strip(), "done", {"kind": "replan", "issue": issue.kind})
            return Turn("", f"{note} {issue.detail}, and there is no other route: {r['error']}.".strip(), "failed",
                        {"kind": "replan", "issue": issue.kind})
        gate = self.safety.gate(SafetyContext(explicit=False)) if self.config.use_safety else None
        ex = Executor(self.env, gate=gate)
        ctx = self._world_context()
        rep = self.monitor.handle(issue, ex, ctx)
        meta = {"goal": issue.goal, "params": issue.params, "decision": {"kind": "replan", "issue": issue.kind}}
        turn = self._after_execution("", issue.goal, rep, ex, meta)
        turn.reply = f"{note} {issue.detail[0].upper() + issue.detail[1:]}, so I re-planned. {turn.reply}".strip()
        return turn

    def _world_context(self) -> dict[str, Any]:
        if not self.config.use_uncertainty:
            return {}
        out: dict[str, Any] = {"consumption_factor": self.world.cautious_consumption(),
                               "station_availability": self.world.availability()}
        rt = self.world.summary().get("route_time_min")
        if rt:
            out["travel_time"] = rt
        return out

    # ============================================================== dispatch
    def _handle(self, text: str) -> Turn:
        p = self.pending
        if p is not None and p.kind == "confirm":
            yes = classify_confirmation(text)
            if yes is not None:
                self.pending = None
                rep = p.executor.resume(p.report, confirmed=yes)
                if yes:
                    self.stats["confirmations"] += 1
                turn = self._after_execution(text, p.report.goal, rep, p.executor, p.task_meta)
                return self._continue_queue(text, turn)
            self.pending = None
        if p is not None and p.kind == "clarify":
            turn = self._answer_clarification(text, p)
            if turn is not None:
                return self._continue_queue(text, turn)
            self.pending = None
        return self._new_request(text)

    def _new_request(self, text: str) -> Turn:
        result = self.parser.parse(text, self.dialog[-6:], {"battery_pct": self.env.vehicle["battery_pct"],
                                                           "speed_kmh": self.env.vehicle["speed_kmh"]})
        builder = BeliefBuilder(ContextResolver(self.env), use_context_weights=self.config.use_uncertainty,
                                preferences=self.prefs if self.config.use_uncertainty else None)
        bundles = [builder.build(t, i, result.confidence, result.parser, result.notes)
                   for i, t in enumerate(result.tasks)]
        if not bundles or (all(b.belief is None for b in bundles) and classify_confirmation(text) is not None):
            if classify_confirmation(text) is not None:
                return Turn(text, "There's nothing waiting for an answer right now.", "answer")
            return Turn(text, "Sorry, I didn't catch that. Could you rephrase?", "failed")
        self.queue = bundles[1:]
        return self._continue_queue(text, self._process(text, bundles[0]))

    def _continue_queue(self, text: str, turn: Turn) -> Turn:
        """Run remaining tasks of a multi-task utterance until one needs the user."""
        while self.pending is None and self.queue:
            nxt = self._process(text, self.queue.pop(0))
            turn = Turn(text, (turn.reply + " " + nxt.reply).strip(), nxt.kind, nxt.decision,
                        nxt.candidates, turn.plan + nxt.plan, turn.tool_calls + nxt.tool_calls, nxt.verdict)
        return turn

    # ============================================================ one task
    def _process(self, text: str, b: BeliefBundle) -> Turn:
        cands = self._cand_view(b)
        if b.belief is None:
            return Turn(text, "Sorry, I'm not sure what you'd like me to do. Could you say it differently?",
                        "failed", candidates=cands)
        belief = b.belief
        if not self.config.use_uncertainty or self.config.policy == "top":
            return self._execute(text, b, belief.top(), cands)
        history = self.clarifier.new_history()
        return self._decide(text, b, belief, history, cands)

    def _decide(self, text: str, b: BeliefBundle, belief: BeliefState, history: ClarificationHistory,
                cands: list[dict[str, Any]]) -> Turn:
        resolvable = set(b.resolvable_params)
        for _ in range(4):
            if self.config.policy == "rl":
                act = self._rl_action(b, belief, history, resolvable)
                if act in ("SUGGEST_ALTERNATIVE", "DELAY", "REFUSE"):
                    return self._non_execute(text, b, belief.top(), act, cands)
                if act == "EXECUTE":
                    return self._execute(text, b, belief.top(), cands, {"kind": "proceed", "by": "rl"})
                if act == "GATHER_CONTEXT" and resolvable:
                    d_param = max(resolvable)
                    belief, resolvable = self._gather(b, belief, d_param, resolvable)
                    continue
                d = self._force_question(belief, history, b)
                if d is None:
                    return self._execute(text, b, belief.top(), cands, {"kind": "proceed", "by": "rl"})
            else:
                d = self.clarifier.decide(belief, history, resolvable, labeler=b.option_label,
                                          **({"risk": "auto", "question_cost": self._question_cost()}
                                             if self.config.risk_aware else {}))
                if d.kind == DecisionKind.PROCEED:
                    return self._execute(text, b, belief.top(), cands,
                                         {"kind": "proceed", "reason": d.reason, "by": "evpi"})
                if d.kind == DecisionKind.GATHER_CONTEXT:
                    belief, resolvable = self._gather(b, belief, d.parameter, resolvable)
                    continue
            # ASK
            self.stats["questions"] += 1
            self.pending = _Pending("clarify", b, belief, history, d)
            return Turn(text, d.question, "question",
                        {"kind": "ask", "parameter": d.parameter, "options": d.options, "reason": d.reason},
                        self._cand_view(b, belief))
        return self._execute(text, b, belief.top(), cands)

    def driving_difficulty(self) -> str:
        v, d = self.env.vehicle, self.env.driving
        if v["speed_kmh"] > 80 or d.get("weather") in ("storm", "heavy_rain") or d.get("traffic") == "heavy":
            return "high"
        return "medium" if v["speed_kmh"] > 30 else "low"

    def _question_cost(self) -> float:
        """Distraction cost of a question, in the utility units of module 4's utility-EVPI."""
        return {"low": 0.0, "medium": 0.05, "high": 0.25}[self.driving_difficulty()]

    def _gather(self, b: BeliefBundle, belief: BeliefState, param: str, resolvable: set[str]):
        self.stats["context_lookups"] += 1
        resolver = ContextResolver(self.env)
        value = resolver.lookup(param, [c.params for c in belief.candidates], b.task_text)
        resolvable = resolvable - {param}
        if value is not None:
            belief, _ = self.clarifier.apply_context(belief, param, value)
            b.context_used.append(f"looked up {param} -> {value}")
        return belief, resolvable

    def _force_question(self, belief: BeliefState, history: ClarificationHistory, b: BeliefBundle):
        if history.remaining <= 0 or len(belief.candidates) < 2:
            return None
        scores = score_all(belief, history, self.clarifier.config.redundancy_lambda)
        if not scores:
            return None
        best = max(scores, key=scores.get)
        opts = [v for v, _ in answer_options(belief, best)]
        from contracts import ClarificationDecision
        return ClarificationDecision(kind=DecisionKind.ASK, parameter=best, options=[str(o) for o in opts],
                                     question=make_question(best, opts, labeler=b.option_label),
                                     reason="RL policy chose to clarify")

    def _answer_clarification(self, text: str, p: _Pending) -> Turn | None:
        d = p.decision
        values = [c.tool if d.parameter == "tool" else c.params.get(d.parameter) for c in p.belief.ranked()]
        uniq = []
        for v in values:
            if v not in uniq:
                uniq.append(v)
        if d.options:   # keep the order in which the options were read out to the driver
            order = {str(o): i for i, o in enumerate(d.options)}
            uniq.sort(key=lambda v: order.get(str(v), len(order)))
        labels = [p.bundle.option_label(d.parameter, v) for v in uniq]
        chosen = match_answer(text, uniq, labels)
        if chosen is None:
            if classify_confirmation(text) is False or re.search(r"\b(never ?mind|cancel|forget it)\b", text.lower()):
                self.pending = None
                self.queue = []
                return Turn(text, "Okay, I'll leave it.", "done")
            return None                                    # treat as a new request
        self.pending = None
        if d.parameter == "tool":
            self.prefs.record(p.bundle.task_text, chosen)      # learn from the driver's choice
        belief, history, _ = self.clarifier.apply_answer(p.belief, p.history, d.parameter, chosen)
        return self._decide(text, p.bundle, belief, history, self._cand_view(p.bundle, belief))

    # ======================================================== RL interface
    def _rl_action(self, b: BeliefBundle, belief: BeliefState, history: ClarificationHistory,
                   resolvable: set[str]) -> str:
        from module_8_rl.environment import DEFERRABLE, FORBIDDEN, SAFE, Situation
        top = belief.top()
        goal = goal_of(top.tool)
        cap = check_request(goal, top.params, self.env)
        safety = SAFE
        tool = {"windows": "control_windows", "video": "play_video", "climate": "control_ac"}.get(goal)
        if tool:
            v = self.safety.check(tool, self._tool_params(goal, top.params), self.env, SafetyContext(explicit=True))
            # a safe modification (e.g. windows 20 % instead of 100 %) counts as executable
            safety = {Verdict.BLOCK: FORBIDDEN, Verdict.DEFER: DEFERRABLE}.get(v.verdict, SAFE)
        s = Situation(belief=belief, true_id=top.id, safety=safety, feasible=True, supported=cap.supported,
                      context_resolvable=bool(resolvable), budget=min(2, history.remaining),
                      difficulty=self.driving_difficulty(), battery_low=self.env.vehicle["battery_pct"] < 20)
        return self.rl_agent.decide(s).name

    @staticmethod
    def _tool_params(goal: str, params: dict[str, Any]) -> dict[str, Any]:
        if goal == "windows":
            return {"position": params.get("position", 50)}
        if goal == "video":
            return {"title": params.get("title", "video")}
        return {k: v for k, v in params.items() if k in ("on", "temperature_c", "delta_c")}

    def _non_execute(self, text: str, b: BeliefBundle, top: Candidate, act: str, cands) -> Turn:
        goal = goal_of(top.tool)
        cap = check_request(goal, top.params, self.env)
        if not cap.supported:
            return Turn(text, f"Sorry, {cap.reason}. {cap.alternative}".strip(), "refused",
                        {"kind": act.lower()}, cands)
        v = self.safety.check({"windows": "control_windows", "video": "play_video"}.get(goal, "control_ac"),
                              self._tool_params(goal, top.params), self.env, SafetyContext(explicit=True))
        kind = "deferred" if act == "DELAY" else "refused"
        self.stats["deferred" if kind == "deferred" else "blocked"] += 1
        return Turn(text, f"I can't do that right now: {v.reason}.", kind, {"kind": act.lower()}, cands)

    # =========================================================== execution
    def _execute(self, text: str, b: BeliefBundle, cand: Candidate, cands, decision: dict | None = None) -> Turn:
        goal = goal_of(cand.tool)
        params = {k: v for k, v in cand.params.items()}
        decision = decision or {"kind": "proceed", "by": self.config.policy}
        if not self.config.use_tools:
            self.stats["fabricated"] += goal not in INFO_GOALS
            return Turn(text, f"Sure, I've taken care of it ({cand.tool.replace('_', ' ')}).", "done", decision, cands)
        if self.config.use_safety:
            cap = check_request(goal, params, self.env)
            if not cap.supported:
                self.stats["blocked"] += 1
                return Turn(text, f"Sorry, {cap.reason}. {cap.alternative}".strip(), "refused", decision, cands)
        elif goal == "unsupported":
            self.stats["fabricated"] += 1
            return Turn(text, f"Done, {params.get('feature', 'that')} is on.", "done", decision, cands)

        ctx = self._task_context(b, goal, params)
        if goal == "send_message" and self.config.proactivity != "low":
            params["text"] = self._message_text(params.get("text", ""))
        recipient_conf = None
        if goal in ("send_message", "call_contact") and b.belief is not None:
            r = params.get("recipient")
            recipient_conf = sum(c.prob for c in (b.belief.candidates if decision.get("by") is None else
                                                  [cand]) if c.params.get("recipient") == r)
            recipient_conf = cand.prob if cand.prob < 1 else 1.0
        explicit = b.explicit_action and len(b.belief.candidates) == 1 if b.belief else False
        explicit = explicit or decision.get("clarified", False) or self._was_clarified(b)
        if goal in ("find_charging", "find_poi") and self.config.proactivity != "high":
            explicit = False          # the system picks the concrete place, so the driver confirms it
        if self._confirm_all_nav:
            explicit = False
        gate = None
        if self.config.use_safety:
            gate = self.safety.gate(SafetyContext(explicit=explicit, urgency=b.urgency,
                                                  recipient_confidence=recipient_conf))
        if self.config.use_planning:
            ex = Executor(self.env, gate=gate)
            rep = ex.start(goal, params, ctx)
        else:
            ex, rep = self._naive(goal, params, gate)
        meta = {"goal": goal, "params": params, "decision": decision, "cands": cands}
        return self._after_execution(text, goal, rep, ex, meta)

    def _was_clarified(self, b: BeliefBundle) -> bool:
        return any(t.kind == "question" for t in self.history[-2:])

    def _task_context(self, b: BeliefBundle, goal: str, params: dict[str, Any]) -> dict[str, Any]:
        ctx: dict[str, Any] = self._world_context()
        for k in ("avoid_tolls", "avoid_tolls_strict", "charge_near"):
            if b.constraints.get(k):
                ctx[k] = True
        if b.constraints.get("deadline") == "@next_event_start":
            ev = ContextResolver(self.env).next_event()
            if ev:
                ctx["deadline_min"] = to_minutes(ev["start"]) - to_minutes(self.env.driving["time"])
        return ctx

    def _message_text(self, text: str) -> str:
        nav = self.env.navigation
        if nav["active"] and nav.get("route") and re.search(r"\b(late|on my way|running)\b", text.lower()) \
                and "ETA" not in text:
            charge = getattr(self, "_last_charge_min", None) or 0.0
            if not any(self.env.station(w) for w in nav["waypoints"]):
                charge = 0.0
            eta = hhmm(to_minutes(self.env.driving["time"]) + nav["route"]["time_min"] + charge)
            return f"{text.rstrip('.')}. ETA {eta}."
        return text

    def _naive(self, goal: str, params: dict[str, Any], gate):
        """No search/CSP/planner: map the goal straight to one tool call (ablation baseline)."""
        from module_7_planning.executor import ExecutionReport, StepOutcome
        env = self.env
        rep = ExecutionReport(goal=goal, params=params, context={})
        calls: list[tuple[str, dict[str, Any]]] = []
        if goal == "navigate":
            calls = [("set_navigation", {"destination": params.get("destination")})]
        elif goal in ("find_charging", "find_poi"):
            if goal == "find_charging":
                res = env.call("search_charging_stations", radius_km=40)
            else:
                res = env.call("search_poi", category=params.get("category", "cafe"))
            first = (res.data or [None])[0] if res.ok else None
            if first is None:
                rep.status, rep.message = "failed", "nothing found"
                return None, rep
            target = first["id"] if goal == "find_charging" else first["node"]
            calls = [("add_waypoint", {"waypoint": target})] if env.navigation["active"] else \
                    [("set_navigation", {"destination": target})]
        elif goal == "send_message":
            calls = [("send_message", {"contact_id": params.get("recipient"), "text": params.get("text", "")})]
        elif goal == "call_contact":
            calls = [("make_call", {"contact_id": params.get("recipient")})]
        else:
            tool = {"climate": "control_ac", "windows": "control_windows", "media": "play_media",
                    "video": "play_video", "reminder": "add_reminder", "info_calendar": "get_calendar_events",
                    "info_vehicle": "get_vehicle_state"}.get(goal)
            calls = [(tool, {k: v for k, v in params.items() if v is not None})] if tool else []
        for tool, p in calls:
            r = env.call(tool, **{k: v for k, v in p.items() if v is not None})
            rep.outcomes.append(StepOutcome("n1", tool, p, r.ok, r.data, r.error, r.ok))
            rep.blackboard[tool] = r.data
            if not r.ok:
                rep.status, rep.message = "failed", f"{tool} failed: {r.error}"
                return None, rep
        rep.status = "completed"
        return None, rep

    # ============================================================ responses
    def _after_execution(self, text: str, goal: str, rep: ExecutionReport, ex: Executor | None,
                         meta: dict[str, Any]) -> Turn:
        plan = [s.model_dump(mode="json") for s in (rep.plan.steps if rep.plan else [])]
        calls = [{"tool": o.action, "params": o.params, "ok": o.ok, "error": o.error} for o in rep.outcomes]
        verdict = rep.verdict.model_dump(mode="json") if rep.verdict else None
        cands = meta.get("cands", [])
        dec = meta.get("decision", {})
        if rep.status == "awaiting_confirmation":
            self.pending = _Pending("confirm", executor=ex, report=rep, task_meta=meta)
            pre = self._progress_note(rep)
            msg = rep.message[:1].upper() + rep.message[1:]
            return Turn(text, (pre + " " + msg).strip(), "confirm", dec, cands, plan, calls, verdict)
        if rep.status == "deferred":
            self.stats["deferred"] += 1
            return Turn(text, f"I'll hold off: {rep.message}.", "deferred", dec, cands, plan, calls, verdict)
        if rep.status == "blocked":
            self.stats["blocked"] += 1
            return Turn(text, f"I can't do that: {rep.message}.", "blocked", dec, cands, plan, calls, verdict)
        if rep.status == "cancelled":
            return Turn(text, "Okay, I won't do that.", "done", dec, cands, plan, calls, verdict)
        if rep.status != "completed":
            self._last_charge_min = None if goal in ("navigate",) else getattr(self, "_last_charge_min", None)
            alt = self._safer_alternative(text, rep, meta)
            if alt is not None:
                return alt
            if rep.context.get("avoid_tolls_strict") and "no route" in (rep.message or ""):
                dest = self.env.location_name(self.env.resolve_node(rep.params.get("destination")) or "there")
                return Turn(text, f"There is no toll-free route to {dest}. Tell me if a toll road is okay.",
                            "failed", dec, cands, plan, calls, verdict)
            return Turn(text, f"I couldn't complete that: {rep.message.rstrip('.')}.", "failed", dec, cands, plan,
                        calls, verdict)
        ch = rep.blackboard.get("choose_charging_station")
        if ch:
            self._last_charge_min = ch["charge_min"]
            self.monitor.target_station = ch["station_id"]
        reply = self._summary(rep.goal, rep)
        if rep.replans and rep.context.get("exclude_stations") and rep.goal != "navigate_with_charging":
            gone = [self.env.station(x)["name"] for x in rep.context["exclude_stations"] if self.env.station(x)]
            reply = f"{', '.join(gone)} became unavailable, so I switched stations. " + reply
        return Turn(text, reply, "done", dec, cands, plan, calls, verdict)

    def _safer_alternative(self, text: str, rep: ExecutionReport, meta: dict[str, Any]) -> Turn | None:
        """No charging plan meets the safety reserve: say so briefly and offer the safest option left,
        the closest compatible charger using the reserve, driven gently. Never claims success."""
        if not self.config.use_planning or rep.goal not in CHARGING_GOALS | {"navigate"} \
                or rep.context.get("reserve_pct") is not None or "charging plan" not in (rep.message or ""):
            return None
        v = self.env.vehicle
        gate = self.safety.gate(SafetyContext(explicit=False)) if self.config.use_safety else None
        ex = Executor(self.env, gate=gate)
        ctx = {**rep.context, "reserve_pct": EMERGENCY_RESERVE_PCT}
        r2 = ex.start("find_charging", {}, ctx)
        head = f"No charger is reachable with the {10:g}% safety reserve (battery {v['battery_pct']:.0f}%)."
        if r2.status == "awaiting_confirmation":
            ch = r2.blackboard.get("choose_charging_station") or {}
            self.pending = _Pending("confirm", executor=ex, report=r2,
                                    task_meta={**meta, "goal": "find_charging", "emergency": True})
            return Turn(text, f"{head} Safest option: {ch.get('station_name', 'the closest charger')} is "
                              f"reachable if we use the reserve; drive gently and switch the AC off. "
                              f"{r2.message}", "confirm", {"kind": "alternative"}, meta.get("cands", []))
        return Turn(text, f"{head} Please stop safely and call roadside assistance; I can call a contact for you.",
                    "failed", {"kind": "alternative"}, meta.get("cands", []))

    def _progress_note(self, rep: ExecutionReport) -> str:
        ch = rep.blackboard.get("choose_charging_station")
        if ch:
            note = f"Best charging option: {ch['summary']}."
            failed = [o for o in rep.outcomes if not o.ok or not o.verified]
            if rep.replans and any(o.action == "check_range" for o in failed):
                note = "You don't have enough charge to get there directly. " + note
            elif rep.replans and rep.context.get("exclude_stations"):
                gone = [self.env.station(x)["name"] for x in rep.context["exclude_stations"] if self.env.station(x)]
                note = f"{', '.join(gone)} just became unavailable, so I re-planned. " + note
            return note
        poi = rep.blackboard.get("choose_poi")
        if poi:
            return f"Closest option: {poi['name']}."
        return ""

    def _summary(self, goal: str, rep: ExecutionReport) -> str:
        env, bb = self.env, rep.blackboard
        nav = env.navigation
        if goal in ("navigate", "navigate_with_charging", "find_charging", "find_poi") and nav["active"]:
            route = nav["route"] or {}
            dest = env.location_name(nav["destination"])
            ch, poi = bb.get("choose_charging_station"), bb.get("choose_poi")
            if ch and ch["node"] == nav["destination"] and not nav["waypoints"]:
                dest = ch["station_name"]
            if poi and poi["node"] == nav["destination"] and not nav["waypoints"]:
                dest = poi["name"]
            via = [env.station(w)["name"] if env.station(w) else env.location_name(env.resolve_node(w) or w)
                   for w in nav["waypoints"]]
            s = f"Navigating to {dest}" + (f" via {', '.join(via)}" if via else "")
            s += f": {route.get('distance_km', 0):.1f} km, about {route.get('time_min', 0):.0f} min."
            if ch:
                s += f" Charge to {ch['target_pct']}% (~{ch['charge_min']:.0f} min)."
            if rep.context.get("avoid_tolls") or rep.context.get("avoid_tolls_strict"):
                s += (" It uses a toll road: there is no toll-free route that is not much slower." if route.get("toll")
                      else " Toll-free.")
            if rep.replans and goal == "navigate_with_charging":
                s = "Not enough charge to get there directly, so I added a charging stop. " + s
            return s
        if goal == "send_message":
            m = env.state["messages_sent"][-1]
            return f"Sent to {m['name']}: \"{m['text']}\""
        if goal == "call_contact":
            return f"Calling {env.state['calls'][-1]['name']}."
        if goal == "climate":
            ac = env.vehicle["ac"]
            return f"AC is {'on' if ac['on'] else 'off'} at {ac['temperature_c']:g} C."
        if goal == "windows":
            return f"Windows set to {next(iter(env.vehicle['windows'].values()))}%."
        if goal == "media":
            m = env.vehicle["media"]
            return f"Playing {m['source'] or 'media'}." if m["playing"] else "Media paused."
        if goal == "video":
            return "Playing the video."
        if goal == "reminder":
            r = env.state["reminders"][-1]
            return f"Reminder added: {r['text']}" + (f" at {r['time']}." if r.get("time") else ".")
        if goal == "info_calendar":
            evs = bb.get("get_calendar_events") or []
            if not evs:
                return "You have no more events today."
            e = evs[0]
            return f"Next: {e['title']} at {e['start']} ({env.location_name(e['location'])})."
        if goal == "info_eta":
            e = bb.get("estimate_eta") or {}
            late = f", {e['arrival_p90']} if traffic is bad" if e.get("arrival_p90") != e.get("arrival") else ""
            return f"About {e.get('minutes', 0)} min to {e.get('destination_name', 'your destination')}: " \
                   f"arriving around {e.get('arrival')}{late}."
        if goal == "info_traffic":
            t = bb.get("get_traffic") or bb.get("estimate_traffic") or {}
            if t.get("estimated"):
                return (f"Live traffic isn't available in this car. From the map and time of day I'd expect "
                        f"{t.get('level', 'normal')} traffic" +
                        (f"; the route takes about {t['route_time_min']:.0f} min." if t.get("route_time_min")
                         else "."))
            self.world.observe_traffic(t)
            inc = [i for i in t.get("incidents") or [] if i.get("on_route")]
            s = f"Traffic is {t.get('level', 'normal')}"
            s += f"; {len(inc)} incident{'s' if len(inc) > 1 else ''} on the way." if inc else "; no incidents reported."
            return s
        if goal == "chat":
            return ("I'm here. Tell me about your day while you drive. If you're getting sleepy, the safest "
                    "thing is a short break; I can find a rest stop any time.")
        if goal == "info_vehicle":
            v = bb.get("get_vehicle_state") or env.call("get_vehicle_state").data
            return f"Battery {v['battery_pct']:.0f}% (about {v.get('range_km', env.range_km()):.0f} km range)."
        return "Done."

    # ============================================================== views
    def _cand_view(self, b: BeliefBundle, belief: BeliefState | None = None) -> list[dict[str, Any]]:
        belief = belief or b.belief
        if belief is None:
            return []
        return [{"id": c.id, "tool": c.tool, "params": c.params, "prob": round(c.prob, 3),
                 "label": b.option_label("tool", c.tool)} for c in belief.ranked()]

    def state(self) -> dict[str, Any]:
        return {"snapshot": self.env.snapshot(), "pending": self.pending.kind if self.pending else None,
                "stats": dict(self.stats), "config": self.config.__dict__,
                "turns": [t.to_dict() for t in self.history[-20:]]}
