"""Calibration of NLU scores (module 3).

NLU scores (rule priors or LLM-stated confidences) are not probabilities. We use
temperature scaling on log-scores, p_i ∝ score_i ** (1/T), fitted by minimising
the negative log-likelihood on labelled examples, and report the expected
calibration error (ECE).
"""
from __future__ import annotations

import math
from typing import Sequence

DEFAULT_TEMPERATURE = 1.0


def apply_temperature(scores: Sequence[float], temperature: float = DEFAULT_TEMPERATURE) -> list[float]:
    if not scores:
        return []
    t = max(temperature, 1e-3)
    logs = [math.log(max(s, 1e-9)) / t for s in scores]
    m = max(logs)
    ex = [math.exp(v - m) for v in logs]
    z = sum(ex)
    return [e / z for e in ex]


def nll(examples: Sequence[tuple[Sequence[float], int]], temperature: float) -> float:
    return -sum(math.log(max(apply_temperature(s, temperature)[y], 1e-12)) for s, y in examples) / max(1, len(examples))


def fit_temperature(examples: Sequence[tuple[Sequence[float], int]],
                    grid: Sequence[float] = tuple(x / 20 for x in range(4, 81))) -> float:
    """examples: (scores, index of the correct candidate). Returns the NLL-optimal T on a grid."""
    return min(grid, key=lambda t: nll(examples, t))


def expected_calibration_error(confidences: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    n = len(confidences)
    if n == 0:
        return 0.0
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if lo < c <= hi or (b == 0 and c == 0)]
        if idx:
            acc = sum(correct[i] for i in idx) / len(idx)
            conf = sum(confidences[i] for i in idx) / len(idx)
            ece += len(idx) / n * abs(acc - conf)
    return ece
