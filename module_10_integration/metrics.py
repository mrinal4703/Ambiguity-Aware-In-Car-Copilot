"""Run scenarios with a simulated user and compute metrics (module 10)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agent import CopilotAgent
from .config import AgentConfig
from .scenarios import MUTATING, Scenario


@dataclass
class TrialResult:
    scenario: str
    category: str
    success: bool
    questions: int
    unnecessary_questions: int
    safety_violation: bool
    fabricated: int
    turns: int
    tool_calls: int
    transcript: list[tuple[str, str]] = field(default_factory=list)


def run_trial(sc: Scenario, config: AgentConfig, seed: int = 0, perturb: bool = False, rl_agent: Any = None,
              max_turns: int = 8) -> TrialResult:
    env = sc.make_env(seed=seed, perturb=perturb)
    agent = CopilotAgent(env, config, rl_agent=rl_agent)
    answers = list(sc.answers)
    queue = list(sc.utterances)
    turns = []
    msg = queue.pop(0)
    for _ in range(max_turns):
        t = agent.handle(msg)
        turns.append(t)
        if t.kind == "question":
            msg = answers.pop(0) if answers else "the first one"
        elif t.kind == "confirm":
            msg = "yes" if sc.confirm else "no"
        elif queue:
            msg = queue.pop(0)
        else:
            break
    questions = sum(t.kind == "question" for t in turns)
    unnecessary = max(0, questions - sc.max_questions) if sc.max_questions is not None else 0
    violation = bool(sc.unsafe(env, turns)) if sc.unsafe else False
    fabricated = agent.stats["fabricated"]
    claimed_done = any(t.kind == "done" for t in turns)
    if claimed_done and not any(r.ok and r.tool in MUTATING for r in env.log) and \
            not any(r.ok for r in env.log) and sc.category not in ("missing_capability",):
        fabricated = max(fabricated, 1)
    return TrialResult(sc.id, sc.category, bool(sc.check(env, turns)), questions, unnecessary, violation,
                       fabricated, len(turns), len(env.log), [(t.user, t.reply) for t in turns])


@dataclass
class Summary:
    config: str
    n: int
    success: float
    pass_at_3: float
    pass_hat_3: float
    questions: float
    unnecessary: float
    safety_violations: float
    hallucinated: float
    by_category: dict[str, float]

    def row(self) -> str:
        return (f"| {self.config} | {self.success:.2f} | {self.pass_at_3:.2f} | {self.pass_hat_3:.2f} | "
                f"{self.questions:.2f} | {self.unnecessary:.2f} | {self.safety_violations:.2f} | "
                f"{self.hallucinated:.2f} |")


HEADER = ("| configuration | task success | Pass@3 | Pass^3 | questions / task | unnecessary q / task | "
          "safety violations / task | hallucinated actions / task |\n|---|---|---|---|---|---|---|---|")


def summarise(name: str, trials: dict[str, list[TrialResult]]) -> Summary:
    flat = [t for ts in trials.values() for t in ts]
    n = len(flat)
    cats: dict[str, list[bool]] = {}
    for t in flat:
        cats.setdefault(t.category, []).append(t.success)
    return Summary(
        name, len(trials), sum(t.success for t in flat) / n,
        sum(any(t.success for t in ts) for ts in trials.values()) / len(trials),
        sum(all(t.success for t in ts) for ts in trials.values()) / len(trials),
        sum(t.questions for t in flat) / n, sum(t.unnecessary_questions for t in flat) / n,
        sum(t.safety_violation for t in flat) / n, sum(t.fabricated > 0 for t in flat) / n,
        {c: sum(v) / len(v) for c, v in sorted(cats.items())})
