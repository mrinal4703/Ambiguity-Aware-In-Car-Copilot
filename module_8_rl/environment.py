"""Decision MDP with a scripted simulated user (module 8).

State  s = (I, U, V, D, H): estimated intent belief (I, U), vehicle/safety status (V),
feasibility and tool support (D) and interaction history / question budget (H).

Actions: EXECUTE, CLARIFY, GATHER_CONTEXT, SUGGEST_ALTERNATIVE, DELAY, REFUSE.

The simulated user holds a hidden goal sampled from the belief, so a calibrated
belief means the top candidate is right with probability `top_prob`.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import IntEnum

from contracts import BeliefState, Candidate

from .reward import DEFAULT_REWARDS, RewardConfig


class Act(IntEnum):
    EXECUTE = 0
    CLARIFY = 1
    GATHER_CONTEXT = 2
    SUGGEST_ALTERNATIVE = 3
    DELAY = 4
    REFUSE = 5


ACTIONS = list(Act)
SAFE, DEFERRABLE, FORBIDDEN = "safe", "deferrable", "forbidden"


@dataclass
class Situation:
    belief: BeliefState
    true_id: str
    safety: str = SAFE                 # safe | deferrable (e.g. windows at speed) | forbidden (video while moving)
    feasible: bool = True              # e.g. enough range / station reachable
    supported: bool = True             # car has the capability
    context_resolvable: bool = False   # a lookup (calendar, route) can resolve the ambiguity
    budget: int = 2
    context_used: bool = False
    questions: int = 0
    steps: int = 0

    def top(self) -> Candidate:
        return self.belief.top()

    @property
    def ambiguous(self) -> bool:
        return len(self.belief.candidates) > 1 and self.top().prob < 0.9


def _bucket(x: float, edges: list[float]) -> int:
    return sum(x >= e for e in edges)


def features(s: Situation) -> tuple[int, ...]:
    """Discrete state used by the Q-table."""
    top = s.top().prob
    margin = s.belief.margin() if len(s.belief.candidates) > 1 else 1.0
    return (_bucket(top, [0.5, 0.7, 0.9]), _bucket(margin, [0.2, 0.5]), min(s.budget, 2),
            [SAFE, DEFERRABLE, FORBIDDEN].index(s.safety), int(s.feasible), int(s.supported),
            int(s.context_resolvable and not s.context_used))


def safety_mask(s: Situation) -> list[bool]:
    """Same gate in training and evaluation: execution is only allowed when module-9 style checks pass."""
    allowed = [True] * len(ACTIONS)
    if s.safety != SAFE or not s.supported:
        allowed[Act.EXECUTE] = False
    if s.budget <= 0:
        allowed[Act.CLARIFY] = False
    return allowed


def gate_fallback(s: Situation) -> Act:
    """What the safety gate does when a policy picks a masked action."""
    if not s.supported:
        return Act.SUGGEST_ALTERNATIVE
    if s.safety == DEFERRABLE:
        return Act.DELAY
    if s.safety == FORBIDDEN:
        return Act.REFUSE
    return Act.EXECUTE if s.budget <= 0 else Act.CLARIFY


@dataclass
class StepResult:
    reward: float
    done: bool
    outcome: str


@dataclass
class DecisionEnv:
    rewards: RewardConfig = DEFAULT_REWARDS
    seed: int | None = None
    max_steps: int = 4
    answer_reliability: float = 0.95
    p_unsafe: float = 0.15
    p_infeasible: float = 0.1
    p_unsupported: float = 0.08
    p_context: float = 0.3
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    # ---------------------------------------------------------------- episodes
    def sample(self) -> Situation:
        r = self.rng
        n = r.choice([1, 1, 2, 2, 3, 4])
        raw = [r.gammavariate(0.8 if n > 1 else 1.0, 1.0) + 1e-3 for _ in range(n)]
        if n > 1 and r.random() < 0.35:            # often one interpretation clearly dominates
            raw[0] += sum(raw) * r.uniform(2, 8)
        tot = sum(raw)
        cands = [Candidate(id=f"c{i}", tool=f"goal_{i}", prob=x / tot) for i, x in enumerate(raw)]
        belief = BeliefState(candidates=cands)
        true = r.choices(cands, weights=[c.prob for c in cands])[0].id
        u = r.random()
        safety = DEFERRABLE if u < self.p_unsafe * 0.6 else FORBIDDEN if u < self.p_unsafe else SAFE
        return Situation(belief=belief, true_id=true, safety=safety,
                         feasible=r.random() >= self.p_infeasible, supported=r.random() >= self.p_unsupported,
                         context_resolvable=n > 1 and r.random() < self.p_context)

    def reset(self) -> Situation:
        self.s = self.sample()
        return self.s

    # ------------------------------------------------------------------- step
    def step(self, a: Act, s: Situation | None = None) -> StepResult:
        s = s or self.s
        R = self.rewards
        s.steps += 1
        nonexec = (not s.supported) or (not s.feasible) or s.safety != SAFE
        if a == Act.EXECUTE:
            if s.safety != SAFE:
                return StepResult(R.unsafe_attempt, True, "unsafe")
            if not s.supported or not s.feasible:
                return StepResult(R.infeasible_proposal, True, "infeasible")
            if s.top().id == s.true_id:
                return StepResult(R.task_success, True, "success")
            return StepResult(R.infeasible_proposal, True, "wrong")
        if a == Act.CLARIFY:
            if s.budget <= 0:
                return self._continue(s, R.wasted_step, "no_budget")
            useful = s.ambiguous and not nonexec
            s.budget -= 1
            s.questions += 1
            self._answer(s)
            return self._continue(s, R.useful_clarification if useful else R.unnecessary_clarification,
                                  "asked" if useful else "unnecessary")
        if a == Act.GATHER_CONTEXT:
            if s.context_resolvable and not s.context_used:
                s.context_used = True
                self._resolve(s, 0.97)
                return self._continue(s, R.context_cost, "context")
            s.context_used = True
            return self._continue(s, R.wasted_step, "context_useless")
        if a == Act.SUGGEST_ALTERNATIVE:
            if not s.supported or not s.feasible:
                return StepResult(R.correct_handling, True, "handled")
            if s.safety != SAFE:
                return StepResult(R.weak_handling, True, "handled_weak")
            return StepResult(R.unnecessary_clarification, True, "missed")
        if a == Act.DELAY:
            if s.safety == DEFERRABLE:
                return StepResult(R.correct_handling, True, "handled")
            if s.safety == FORBIDDEN:
                return StepResult(R.weak_handling, True, "handled_weak")
            return StepResult(R.unnecessary_clarification, True, "missed")
        if a == Act.REFUSE:
            if s.safety == FORBIDDEN:
                return StepResult(R.correct_handling, True, "handled")
            if nonexec:
                return StepResult(R.weak_handling, True, "handled_weak")
            return StepResult(R.infeasible_proposal, True, "missed")
        raise ValueError(a)

    def _continue(self, s: Situation, reward: float, outcome: str) -> StepResult:
        if s.steps >= self.max_steps:
            return StepResult(reward + self.rewards.timeout, True, "timeout")
        return StepResult(reward, False, outcome)

    def _answer(self, s: Situation) -> None:
        """Simulated user answers truthfully with probability `answer_reliability`."""
        correct = self.rng.random() < self.answer_reliability
        self._resolve(s, 0.95 if correct else 0.6, wrong=not correct)

    def _resolve(self, s: Situation, conf: float, wrong: bool = False) -> None:
        ids = [c.id for c in s.belief.candidates]
        if len(ids) == 1:
            return
        target = s.true_id if not wrong else self.rng.choice([i for i in ids if i != s.true_id])
        rest = (1 - conf) / (len(ids) - 1)
        s.belief = BeliefState(candidates=[c.model_copy(update={"prob": conf if c.id == target else rest})
                                           for c in s.belief.candidates])


SUCCESS_OUTCOMES = {"success", "handled"}
