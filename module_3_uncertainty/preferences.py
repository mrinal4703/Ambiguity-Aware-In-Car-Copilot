"""Driver preferences learned from previous choices (module 3).

A Dirichlet-multinomial model per *trigger* (the kind of request, e.g. "tea",
"tired", "hot"): every time the driver picks an interpretation, its count goes up.
The posterior mean is used as a prior multiplier on the NLU candidates, so after
the driver has chosen the same option twice for "I need tea", the copilot becomes
confident enough to skip the question (EVPI decides), while one odd choice does
not flip the behaviour. Static profile preferences (preferred charging network,
toll avoidance) live here too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

TRIGGERS = {
    "tea": r"\b(tea|chai|coffee)\b", "tired": r"\b(tired|sleepy|drowsy|exhausted|fatigued)\b",
    "hot": r"\b(hot|warm|stuffy|boiling|sweating|humid)\b", "cold": r"\b(cold|freezing|chilly)\b",
    "stop": r"\b(stop|break|pull over)\b", "late": r"\b(late|behind schedule)\b",
}


def trigger_of(text: str) -> str | None:
    t = text.lower()
    return next((k for k, pat in TRIGGERS.items() if re.search(pat, t)), None)


@dataclass
class PreferenceModel:
    alpha: float = 1.0                     # symmetric Dirichlet prior
    prior_strength: float = 0.5            # pseudo-count weight of the parser prior (a0)
    counts: dict[str, dict[str, float]] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=lambda: {"preferred_network": None, "avoid_tolls": False})

    def record(self, text: str, choice: str) -> None:
        trig = trigger_of(text)
        if trig:
            c = self.counts.setdefault(trig, {})
            c[choice] = c.get(choice, 0.0) + 1.0

    def weight(self, text: str, choice: str, options: list[str], prior: float | None = None) -> float:
        """Posterior / prior for `choice` (1.0 = no learned preference).

        With `prior` (the parser's probability) the Dirichlet uses the prior as pseudo-counts
        of strength `prior_strength`:  p(o | choices) = (a0 * prior_o + n_o) / (a0 + N).
        Without it, a symmetric Dirichlet(alpha) relative to uniform is used."""
        trig = trigger_of(text)
        if not trig or trig not in self.counts or not options:
            return 1.0
        c = self.counts[trig]
        opts = set(options)
        n = sum(c.get(o, 0.0) for o in opts)
        if prior is not None and prior > 0:
            a0 = self.prior_strength
            return ((a0 * prior + c.get(choice, 0.0)) / (a0 + n)) / prior
        k = len(opts)
        post = (c.get(choice, 0.0) + self.alpha) / (n + self.alpha * k)
        return post * k
