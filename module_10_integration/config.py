"""Agent configuration and ablation presets (module 10, owner: Souymadeep)."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class AgentConfig:
    use_tools: bool = True          # False = "LLM alone": answers without calling any tool
    use_uncertainty: bool = True    # modules 3+4: beliefs, context lookup, EVPI clarification
    use_planning: bool = True       # modules 5+6+7: search, CSP, planner/executor with replanning
    use_safety: bool = True         # module 9: capability + policy gate + verification
    policy: str = "evpi"            # "top" | "evpi" | "rl"
    proactivity: str = "medium"     # "low" | "medium" | "high"
    parser: str = "rules"           # "rules" | "llm" | "auto"
    question_budget: int = 3
    risk_aware: bool = True         # module 4: execute threshold and question cost depend on risk / driving load
    responder: str = "template"     # "template" | "llm" (grounded rephrasing, falls back to the template)

    def with_(self, **kw) -> "AgentConfig":
        return replace(self, **kw)


FULL_FIXED = AgentConfig()
ABLATIONS: dict[str, AgentConfig] = {
    "llm_alone": AgentConfig(use_tools=False, use_uncertainty=False, use_planning=False, use_safety=False,
                             policy="top"),
    "llm_tools": AgentConfig(use_uncertainty=False, use_planning=False, use_safety=False, policy="top"),
    "llm_uncertainty": AgentConfig(use_planning=False, use_safety=False, policy="evpi"),
    "llm_planning": AgentConfig(use_uncertainty=False, use_safety=False, policy="top"),
    "full_fixed": FULL_FIXED,
    "full_rl": AgentConfig(policy="rl"),
}
