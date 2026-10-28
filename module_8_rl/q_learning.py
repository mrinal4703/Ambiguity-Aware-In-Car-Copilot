"""Tabular Q-learning with the safety mask applied in training and evaluation (module 8)."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .environment import ACTIONS, Act, DecisionEnv, Situation, features, safety_mask


@dataclass
class QAgent:
    alpha: float = 0.1
    gamma: float = 0.95
    epsilon: float = 1.0
    epsilon_min: float = 0.05
    epsilon_decay: float | None = None    # default: reach epsilon_min after 60 % of the episodes
    seed: int | None = 0
    q: dict[tuple, list[float]] = field(default_factory=lambda: defaultdict(lambda: [0.0] * len(ACTIONS)))

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def act(self, s: Situation, explore: bool = False) -> Act:
        mask = safety_mask(s)
        allowed = [a for a in ACTIONS if mask[a]]
        if explore and self.rng.random() < self.epsilon:
            return self.rng.choice(allowed)
        qs = self.q[features(s)]
        return max(allowed, key=lambda a: (qs[a], -a))

    def decide(self, s: Situation) -> Act:
        return self.act(s, explore=False)

    def update(self, f: tuple, a: Act, r: float, f2: tuple | None, mask2: list[bool] | None) -> None:
        target = r
        if f2 is not None:
            target += self.gamma * max(v for v, ok in zip(self.q[f2], mask2) if ok)
        self.q[f][a] += self.alpha * (target - self.q[f][a])

    def train(self, env: DecisionEnv, episodes: int = 20000) -> list[float]:
        returns = []
        decay = self.epsilon_decay or (self.epsilon_min / max(self.epsilon, 1e-9)) ** (1 / max(1, 0.6 * episodes))
        for _ in range(episodes):
            s = env.reset()
            total, done = 0.0, False
            while not done:
                f = features(s)
                a = self.act(s, explore=True)
                res = env.step(a, s)
                total += res.reward
                done = res.done
                self.update(f, a, res.reward, None if done else features(s), None if done else safety_mask(s))
            self.epsilon = max(self.epsilon_min, self.epsilon * decay)
            returns.append(total)
        return returns

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({",".join(map(str, k)): v for k, v in self.q.items()}))

    @classmethod
    def load(cls, path: str | Path) -> "QAgent":
        ag = cls(epsilon=0.0)
        for k, v in json.loads(Path(path).read_text()).items():
            ag.q[tuple(int(x) for x in k.split(","))] = v
        return ag

    def policy_table(self) -> dict[tuple, str]:
        return {k: Act(max(range(len(v)), key=v.__getitem__)).name for k, v in self.q.items()}
