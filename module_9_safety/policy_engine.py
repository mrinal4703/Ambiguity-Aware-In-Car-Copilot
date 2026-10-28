"""Safety and policy engine (module 9, owner: Nishkarsh).

Every tool step is checked *before* execution, independently of the LLM:

1. capability      tool exists and the car has the feature          -> BLOCK
2. parameters      required parameters present and resolved         -> DEFER (ask)
3. validity        AC 16-30 C, windows 0-100 %                       -> MODIFY (closest valid value) / BLOCK
4. driving safety  video while moving                                -> BLOCK
                   windows > 20 % above 80 km/h                      -> MODIFY ("open to 20 % instead?")

MODIFY is a CONFIRM verdict carrying `modified_params`: the closest safe value found
by module 6's setting CSP. The executor applies it only after the driver agrees.
5. authorization   contact allows messages, recipient confidence    -> BLOCK
6. workload        high driving difficulty defers non-urgent comms  -> DEFER
7. confirmation    consequential actions need explicit confirmation -> CONFIRM
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts import Plan, PlanStep, SafetyClass, SafetyVerdict, Verdict
from module_1_simulator.tool_specs import TOOL_SPECS

from module_6_csp import solve_setting, window_domain, ac_domain

from .capability_checker import tool_supported

INTERNAL_ACTIONS = {"check_range", "choose_charging_station", "choose_poi", "resolve_contact", "compose_answer"}
COMMS = {"send_message", "make_call"}
NAVIGATION = {"set_navigation", "add_waypoint", "cancel_navigation"}


@dataclass
class SafetyConfig:
    ac_min_c: float = 16.0
    ac_max_c: float = 30.0
    window_max_pct_at_speed: int = 20
    window_speed_kmh: float = 80.0
    recipient_min_confidence: float = 0.9
    confirm_navigation_when_inferred: bool = True
    defer_comms_when_difficult: bool = True


@dataclass
class SafetyContext:
    explicit: bool = False                 # user explicitly asked for exactly this action
    urgency: str = "normal"
    recipient_confidence: float | None = None
    confirmed: bool = False


@dataclass
class SafetyPolicy:
    config: SafetyConfig = field(default_factory=SafetyConfig)

    def setting_limits(self, action: str, env: Any) -> list[tuple[str, Any]]:
        """Hard limits on a setting in the current situation (used by the setting CSP)."""
        cfg = self.config
        if action == "control_ac":
            return [("supported_range", lambda x: cfg.ac_min_c <= x <= cfg.ac_max_c)]
        if action == "control_windows":
            lim = [("valid_range", lambda x: 0 <= x <= 100)]
            if env.vehicle["speed_kmh"] > cfg.window_speed_kmh:
                lim.append(("safe_at_speed", lambda x: x <= cfg.window_max_pct_at_speed))
            return lim
        return []

    def check(self, action: str, params: dict[str, Any], env: Any, ctx: SafetyContext | None = None,
              step_id: str | None = None) -> SafetyVerdict:
        ctx = ctx or SafetyContext()
        cfg = self.config
        V = lambda v, r: SafetyVerdict(verdict=v, reason=r, step_id=step_id)
        if action in INTERNAL_ACTIONS:
            return V(Verdict.ALLOW, "internal computation")

        # 1. capability
        cap = tool_supported(action, env)
        if not cap.supported:
            return V(Verdict.BLOCK, cap.reason + (f". {cap.alternative}" if cap.alternative else ""))
        spec = TOOL_SPECS[action]

        # 2. parameters
        missing = [p for p in spec.required if params.get(p) in (None, "")]
        unresolved = [k for k, v in params.items() if isinstance(v, str) and v[:1] in ("@", "$")]
        if missing or unresolved:
            return V(Verdict.DEFER, f"missing information: {', '.join(missing + unresolved)}")

        v = env.vehicle
        speed = v["speed_kmh"]
        # 3. validity
        if action == "control_ac":
            target = v["ac"]["temperature_c"]
            if params.get("delta_c") is not None:
                target += float(params["delta_c"])
            if params.get("temperature_c") is not None:
                target = float(params["temperature_c"])
            if not cfg.ac_min_c <= target <= cfg.ac_max_c:
                fix = solve_setting(target, ac_domain(), self.setting_limits(action, env))
                why = f"{target:g} C is outside the supported {cfg.ac_min_c:g}-{cfg.ac_max_c:g} C range"
                if fix.feasible and not ctx.confirmed:
                    return SafetyVerdict(verdict=Verdict.CONFIRM, step_id=step_id,
                                         reason=f"{why}. Set it to {fix.value:g} C instead?",
                                         modified_params={"temperature_c": fix.value, "delta_c": None})
                return V(Verdict.BLOCK, why)
        if action == "control_windows":
            pos = int(params["position"])
            limits = self.setting_limits(action, env)
            broken = [n for n, ok in limits if not ok(pos)]
            if broken:
                fix = solve_setting(pos, window_domain(), limits)
                if "valid_range" in broken or not fix.feasible:
                    return V(Verdict.BLOCK, "window position must be between 0 and 100 %")
                # 4. driving safety -> modify instead of refusing
                if not ctx.confirmed:
                    return SafetyVerdict(
                        verdict=Verdict.CONFIRM, step_id=step_id, modified_params={"position": int(fix.value)},
                        reason=(f"opening the windows to {pos}% above {cfg.window_speed_kmh:g} km/h is unsafe. "
                                f"Open them to {int(fix.value)}% instead?"))
                return V(Verdict.DEFER, f"opening the windows more than {cfg.window_max_pct_at_speed}% above "
                                        f"{cfg.window_speed_kmh:g} km/h is unsafe; I can do it when you slow down")
            if pos > 0 and env.driving.get("weather") == "rain" and not ctx.confirmed:
                return V(Verdict.CONFIRM, "it is raining; open the windows anyway?")
        if action == "play_video" and speed > 0:
            return V(Verdict.BLOCK, "video playback is only allowed while parked")

        # 5. authorization
        if action in COMMS:
            c = env.contact(params.get("contact_id"))
            if c is None:
                return V(Verdict.BLOCK, f"unknown contact '{params.get('contact_id')}'")
            if action == "send_message" and not c.get("allow_messages", True):
                return V(Verdict.BLOCK, f"{c['name']} is not on the list of contacts I may message")
            if ctx.recipient_confidence is not None and ctx.recipient_confidence < cfg.recipient_min_confidence:
                return V(Verdict.BLOCK, f"not sure enough who the recipient is "
                                        f"({ctx.recipient_confidence:.0%} < {cfg.recipient_min_confidence:.0%})")
        # 6. workload
        if (cfg.defer_comms_when_difficult and action in COMMS and ctx.urgency != "high"
                and env.driving.get("driving_difficulty") == "high"):
            return V(Verdict.DEFER, "driving conditions are demanding; I'll do this when it is calmer")

        # 7. confirmation
        if not ctx.confirmed:
            if spec.requires_confirmation:
                return V(Verdict.CONFIRM, _confirm_text(action, params, env))
            if action == "set_navigation" and params.get("waypoints"):
                return V(Verdict.CONFIRM, _confirm_text(action, params, env))   # stops added by the system
            if spec.safety_class == SafetyClass.CONSEQUENTIAL and not ctx.explicit \
                    and cfg.confirm_navigation_when_inferred:
                return V(Verdict.CONFIRM, _confirm_text(action, params, env))
            if spec.safety_class == SafetyClass.CRITICAL and not ctx.explicit:
                return V(Verdict.CONFIRM, _confirm_text(action, params, env))
        return V(Verdict.ALLOW, "passed all checks")

    def check_step(self, step: PlanStep, params: dict[str, Any] | None, env: Any,
                   ctx: SafetyContext | None = None) -> SafetyVerdict:
        return self.check(step.action, params if params is not None else step.params, env, ctx, step.id)

    def check_plan(self, plan: Plan, env: Any, ctx: SafetyContext | None = None) -> list[SafetyVerdict]:
        """Static pre-check (parameter references to earlier steps are not treated as missing)."""
        out = []
        for s in plan.steps:
            params = {k: ("<ref>" if isinstance(v, str) and v.startswith("$") else v) for k, v in s.params.items()}
            if s.action in COMMS and params.get("contact_id") == "<ref>":
                out.append(SafetyVerdict(verdict=Verdict.CONFIRM, reason="message needs confirmation", step_id=s.id))
                continue
            out.append(self.check(s.action, params, env, ctx, s.id))
        return out

    def gate(self, ctx: SafetyContext | None = None):
        """Adapter for module 7's Executor(gate=...)."""
        base = ctx or SafetyContext()

        def _gate(step: PlanStep, params: dict[str, Any], env: Any, confirmed: bool) -> SafetyVerdict:
            c = SafetyContext(base.explicit, base.urgency, base.recipient_confidence, confirmed or base.confirmed)
            return self.check_step(step, params, env, c)
        return _gate


def _confirm_text(action: str, params: dict[str, Any], env: Any) -> str:
    if action == "send_message":
        c = env.contact(params["contact_id"])
        return f"Send \"{params['text']}\" to {c['name'] if c else params['contact_id']}?"
    if action == "make_call":
        c = env.contact(params["contact_id"])
        return f"Call {c['name'] if c else params['contact_id']}?"
    if action == "set_navigation":
        st = env.station(params["destination"])
        d = env.resolve_node(params["destination"]) or params["destination"]
        via = params.get("waypoints") or []
        names = [env.station(w)["name"] if env.station(w) else env.location_name(w) for w in via]
        return f"Start navigation to {st['name'] if st else env.location_name(d)}" + (f" via {', '.join(names)}" if names else "") + "?"
    if action == "add_waypoint":
        w = params["waypoint"]
        name = env.station(w)["name"] if env.station(w) else env.location_name(env.resolve_node(w) or w)
        return f"Add a stop at {name}?"
    if action == "cancel_navigation":
        return "Cancel the current navigation?"
    if action == "control_windows":
        return f"Open the windows to {params['position']}%?"
    return f"Run {action.replace('_', ' ')}?"
