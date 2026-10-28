"""Turn NLU tasks into calibrated belief states (module 3).

Pipeline for one `Task` (module 2):
  1. calibrate the NLU scores into probabilities (temperature scaling),
  2. re-weight candidates with driving/vehicle context (e.g. low battery makes a
     charging stop more plausible; opening windows at 100 km/h less plausible),
  3. ground references through `ContextResolver`; a reference with several
     possible values splits the candidate into weighted alternatives,
  4. report uncertainty, separating
       * aleatoric / request ambiguity : spread of the belief over interpretations
       * epistemic / model uncertainty : how much the parser itself can be trusted
         (parser confidence, fallback use, unknown intent, missing parameters).

The output `BeliefBundle` carries the `BeliefState` (shared contract) consumed by
module 4 (EVPI clarification) and module 8 (RL features).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from contracts import BeliefState, Candidate

from .calibration import DEFAULT_TEMPERATURE, apply_temperature
from .context_resolver import ContextResolver


@dataclass
class UncertaintyReport:
    aleatoric_entropy_bits: float
    epistemic: float                      # 0 = parser fully trusted, 1 = no trust
    top_prob: float
    margin: float
    n_candidates: int
    missing_params: list[str]
    reasons: list[str] = field(default_factory=list)

    @property
    def is_ambiguous(self) -> bool:
        return self.n_candidates > 1 and self.top_prob < 0.8


@dataclass
class BeliefBundle:
    task_index: int
    task_text: str
    belief: BeliefState | None
    report: UncertaintyReport
    labels: dict[str, dict[str, str]] = field(default_factory=dict)   # cand_id -> {param: label}
    resolvable_params: set[str] = field(default_factory=set)
    context_used: list[str] = field(default_factory=list)
    explicit_action: bool = False
    urgency: str = "normal"
    constraints: dict[str, Any] = field(default_factory=dict)
    intent: str = "unknown"

    def option_label(self, param: str, value: Any) -> str:
        for cid, labels in self.labels.items():
            cand = next((c for c in self.belief.candidates if c.id == cid), None) if self.belief else None
            if cand is not None and param in labels:
                v = cand.tool if param == "tool" else cand.params.get(param)
                if v == value:
                    return labels[param]
        return str(value).replace("_", " ")


# ------------------------------------------------------------------ re-weighting
def context_weight(goal: str, params: dict[str, Any], vehicle: dict[str, Any], driving: dict[str, Any]) -> tuple[float, str]:
    """Multiplicative plausibility adjustment from the current situation."""
    battery = vehicle.get("battery_pct", 50)
    speed = vehicle.get("speed_kmh", 0)
    outside = driving.get("outside_temperature_c", 25)
    if goal == "find_charging":
        if battery < 25:
            return 3.0, f"battery {battery:.0f}% is low"
        if battery > 60:
            return 0.5, f"battery {battery:.0f}% is high"
    if goal == "windows" and params.get("position", 0) > 0:
        w, why = 1.0, []
        if speed > 60:
            w *= 0.3; why.append(f"speed {speed:.0f} km/h")
        if driving.get("weather") == "rain":
            w *= 0.3; why.append("rain")
        if outside > 30:
            w *= 0.5; why.append(f"outside {outside:.0f} C")
        return w, ", ".join(why)
    if goal == "climate" and params.get("delta_c", 0) < 0 and outside > 30:
        return 2.0, f"outside {outside:.0f} C makes AC the better cooling option"
    return 1.0, ""


# ------------------------------------------------------------------ builder
class BeliefBuilder:
    def __init__(self, resolver: ContextResolver, temperature: float = DEFAULT_TEMPERATURE,
                 use_context_weights: bool = True):
        self.resolver = resolver
        self.temperature = temperature
        self.use_context_weights = use_context_weights

    def build(self, task, task_index: int = 0, parser_confidence: float = 0.9,
              parser_name: str = "rules", notes: list[str] | None = None) -> BeliefBundle:
        reasons: list[str] = []
        if not task.candidates:
            report = UncertaintyReport(0.0, 1.0, 0.0, 0.0, 0, [], ["intent could not be identified"])
            return BeliefBundle(task_index, task.text, None, report, intent=task.intent,
                                explicit_action=task.explicit_action)

        probs = apply_temperature([c.score for c in task.candidates], self.temperature)
        vehicle = self.resolver.vehicle() if self.use_context_weights else {}
        driving = self.resolver.driving() if self.use_context_weights else {}

        grounded: list[tuple[str, dict[str, Any], float, dict[str, str]]] = []
        for cand, p in zip(task.candidates, probs):
            w, why = (context_weight(cand.goal, cand.params, vehicle, driving)
                      if self.use_context_weights else (1.0, ""))
            if w != 1.0 and why:
                reasons.append(f"{cand.goal} x{w:g} ({why})")
            for params, weight, labels in self._ground(cand.params, task.text):
                grounded.append((cand.goal, params, p * w * weight, labels))

        # merge duplicates (same goal and params after grounding)
        merged: dict[str, tuple[str, dict[str, Any], float, dict[str, str]]] = {}
        for goal, params, p, labels in grounded:
            key = goal + repr(sorted(params.items(), key=lambda kv: kv[0]))
            if key in merged:
                g, pr, q, lb = merged[key]
                merged[key] = (g, pr, q + p, lb)
            else:
                merged[key] = (goal, params, p, labels)
        items = [v for v in merged.values() if v[2] > 0]
        cands = [Candidate(id=f"t{task_index}c{i}", tool=tool_name(g, pr), params=pr, prob=max(p, 1e-9))
                 for i, (g, pr, p, _) in enumerate(items)]
        belief = BeliefState(candidates=cands)
        labels = {c.id: {**items[i][3], "tool": _goal_label(c.tool, c.params)} for i, c in enumerate(cands)}

        missing = sorted({k for c in cands for k, v in c.params.items() if v is None and k != "time"})
        epistemic = 1.0 - parser_confidence
        if parser_name != "llm" and notes:
            epistemic = min(1.0, epistemic + 0.2)
            reasons.append("LLM output rejected; rule fallback used")
        if missing:
            epistemic = min(1.0, epistemic + 0.1 * len(missing))
            reasons.append(f"missing parameters: {missing}")

        cand_dicts = [c.params for c in cands]
        resolvable = {p for p in _differing(cands) if p != "tool"
                      and self.resolver.can_lookup(p, cand_dicts, task.text)}
        report = UncertaintyReport(
            aleatoric_entropy_bits=belief.entropy_bits(), epistemic=round(epistemic, 3),
            top_prob=belief.top().prob, margin=belief.margin(), n_candidates=len(cands),
            missing_params=missing, reasons=reasons)
        return BeliefBundle(task_index, task.text, belief, report, labels, resolvable,
                            [f"{l.tool}({l.params}) -> {l.summary}" for l in self.resolver.log],
                            task.explicit_action, task.urgency, dict(task.constraints), task.intent)

    def _ground(self, params: dict[str, Any], text: str):
        """Cartesian expansion of referenced parameters into weighted alternatives."""
        options: list[tuple[dict[str, Any], float, dict[str, str]]] = [({}, 1.0, {})]
        for k, v in params.items():
            alts = self.resolver.resolve(k, v, text)
            if alts is None:
                options = [({**p, k: v}, w, lb) for p, w, lb in options]
            elif not alts:
                options = [({**p, k: None}, w, lb) for p, w, lb in options]
            else:
                total = sum(a.weight for a in alts)
                options = [({**p, k: a.value}, w * a.weight / total, {**lb, k: a.label or str(a.value)})
                           for p, w, lb in options for a in alts]
        return options


def tool_name(goal: str, params: dict[str, Any]) -> str:
    """POI searches get distinct names (find_cafe, find_rest_area) so that the
    "what would you like me to do" question separates them."""
    if goal == "find_poi" and params.get("category"):
        return f"find_{params['category']}"
    return goal


def goal_of(tool: str) -> str:
    """Inverse of tool_name."""
    return "find_poi" if tool.startswith("find_") and tool != "find_charging" else tool


def _differing(cands: list[Candidate]) -> list[str]:
    keys = {"tool"} | {k for c in cands for k in c.params}
    out = []
    for k in keys:
        vals = {repr(c.tool if k == "tool" else c.params.get(k)) for c in cands}
        if len(vals) > 1:
            out.append(k)
    return sorted(out)


_GOAL_LABELS = {"find_poi": {"cafe": "find a tea/coffee shop", "rest_area": "find a rest stop",
                             "pharmacy": "find a pharmacy", "hospital": "find a hospital"},
                "find_charging": "find a charging stop", "reminder": "add a reminder", "navigate": "navigate there",
                "climate": "adjust the AC", "windows": "open the windows", "send_message": "send a message",
                "call_contact": "make a call", "media": "play media"}


def _goal_label(goal: str, params: dict[str, Any]) -> str:
    goal = goal_of(goal)
    lab = _GOAL_LABELS.get(goal, goal.replace("_", " "))
    if isinstance(lab, dict):
        return lab.get(params.get("category"), goal)
    if goal == "navigate" and params.get("destination"):
        return f"navigate to {params['destination'].replace('_', ' ')}"
    return lab


def entropy(ps: list[float]) -> float:
    return -sum(p * math.log2(p) for p in ps if p > 0)
