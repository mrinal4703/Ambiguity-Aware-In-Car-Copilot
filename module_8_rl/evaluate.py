"""Train Q-learning and compare with baselines: `python -m module_8_rl.evaluate`."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .environment import SUCCESS_OUTCOMES, Act, DecisionEnv, gate_fallback, safety_mask
from .policies import baselines
from .q_learning import QAgent
from .reward import DEFAULT_REWARDS, SENSITIVITY, RewardConfig


@dataclass
class Metrics:
    policy: str
    reward: float
    success: float
    questions: float
    unnecessary: float
    gate_interventions: float
    wrong_or_infeasible: float

    def row(self) -> str:
        return (f"| {self.policy} | {self.reward:.2f} | {self.success:.3f} | {self.questions:.2f} | "
                f"{self.unnecessary:.2f} | {self.gate_interventions:.3f} | {self.wrong_or_infeasible:.3f} |")


HEADER = ("| policy | mean reward | success | questions | unnecessary q | gate interventions | wrong/infeasible |\n"
          "|---|---|---|---|---|---|---|")


def run_episode(policy, env: DecisionEnv, use_gate: bool = True) -> dict[str, float]:
    s = env.reset()
    total, interventions, unnecessary, done, outcome = 0.0, 0, 0, False, ""
    while not done:
        a = policy.decide(s)
        if use_gate and not safety_mask(s)[a]:
            interventions += 1
            a = gate_fallback(s)
        res = env.step(a, s)
        total += res.reward
        unnecessary += res.outcome == "unnecessary"
        done, outcome = res.done, res.outcome
    return {"reward": total, "success": outcome in SUCCESS_OUTCOMES, "questions": s.questions,
            "unnecessary": unnecessary, "gate": interventions, "wrong": outcome in ("wrong", "infeasible")}


def evaluate_policy(policy, rewards: RewardConfig = DEFAULT_REWARDS, episodes: int = 3000, seed: int = 123,
                    use_gate: bool = True, name: str | None = None) -> Metrics:
    env = DecisionEnv(rewards=rewards, seed=seed)
    rows = [run_episode(policy, env, use_gate) for _ in range(episodes)]
    m = lambda k: sum(float(r[k]) for r in rows) / episodes
    return Metrics(name or getattr(policy, "name", type(policy).__name__), m("reward"), m("success"),
                   m("questions"), m("unnecessary"), m("gate"), m("wrong"))


def train_agent(rewards: RewardConfig = DEFAULT_REWARDS, episodes: int = 80000, seed: int = 0) -> QAgent:
    agent = QAgent(seed=seed)
    agent.train(DecisionEnv(rewards=rewards, seed=seed + 1000), episodes)
    agent.epsilon = 0.0
    agent.name = "q_learning"
    return agent


def compare(rewards: RewardConfig = DEFAULT_REWARDS, train_episodes: int = 80000,
            eval_episodes: int = 3000) -> list[Metrics]:
    agent = train_agent(rewards, train_episodes)
    return [evaluate_policy(p, rewards, eval_episodes) for p in baselines()] + \
           [evaluate_policy(agent, rewards, eval_episodes)]


def sensitivity(train_episodes: int = 50000, eval_episodes: int = 2000) -> dict[str, list[Metrics]]:
    out = {}
    for name, cfg in SENSITIVITY.items():
        agent = train_agent(cfg, train_episodes)
        out[name] = [evaluate_policy(agent, cfg, eval_episodes),
                     evaluate_policy(baselines()[3], cfg, eval_episodes),
                     evaluate_policy(baselines()[4], cfg, eval_episodes)]
    return out


def main() -> None:
    print("## Policy comparison (same safety gate for every policy)\n")
    print(HEADER)
    for m in compare():
        print(m.row())
    print("\n## Reward sensitivity (Q-learning vs EVPI vs hybrid rules)\n")
    for name, rows in sensitivity().items():
        print(f"\n### {name}\n")
        print(HEADER)
        for m in rows:
            print(m.row())


if __name__ == "__main__":
    main()
