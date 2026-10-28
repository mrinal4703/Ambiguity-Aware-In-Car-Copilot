"""Clarification evaluation (module 4, milestones M4.6 / M4.7).

Run:  python -m module_4_evpi.evaluate

A simulated driver has a hidden true candidate drawn from the belief (so the
belief is calibrated by construction) and answers each question truthfully with
the true value of the asked parameter. Optional context lookups reveal the true
value of `resolvable` parameters for free.

Metrics per policy:
  success rate        final executed candidate == true candidate
  questions / dialog  number of questions asked
  useful questions    questions whose answer changed the top candidate or removed doubt
  unnecessary         questions asked although the top candidate was already the true one
                      with probability >= 0.8 (i.e. the answer could not change the decision much)
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from contracts import BeliefState, Candidate, ClarificationHistory, DecisionKind

from .baselines import ALL_POLICIES
from .evpi import TOOL_PARAM, _value, update_with_answer


@dataclass
class ClarScenario:
    name: str
    belief: BeliefState
    resolvable: set[str] = field(default_factory=set)


def handmade() -> list[ClarScenario]:
    C = Candidate
    return [
        ClarScenario("tea", BeliefState(candidates=[C(id="a", tool="find_cafe", prob=.55),
                                                    C(id="b", tool="find_rest_area", prob=.25),
                                                    C(id="c", tool="reminder", prob=.15),
                                                    C(id="d", tool="navigate", prob=.05)])),
        ClarScenario("late_message", BeliefState(candidates=[
            C(id="a", tool="send_message", params={"recipient": "priya"}, prob=.55),
            C(id="b", tool="send_message", params={"recipient": "rahul_v"}, prob=.45)])),
        ClarScenario("rahul_calendar", BeliefState(candidates=[
            C(id="a", tool="send_message", params={"recipient": "rahul_v"}, prob=.55),
            C(id="b", tool="send_message", params={"recipient": "rahul_d"}, prob=.45)]), {"recipient"}),
        ClarScenario("hot_ac", BeliefState(candidates=[C(id="a", tool="climate", prob=.88),
                                                       C(id="b", tool="windows", prob=.12)])),
        ClarScenario("two_param", BeliefState(candidates=[
            C(id="a", tool="t", params={"p1": "A", "p2": "x"}, prob=.5),
            C(id="b", tool="t", params={"p1": "A", "p2": "y"}, prob=.3),
            C(id="c", tool="t", params={"p1": "B", "p2": "x"}, prob=.2)])),
        ClarScenario("stop_somewhere", BeliefState(candidates=[C(id="a", tool="find_rest_area", prob=.4),
                                                               C(id="b", tool="find_cafe", prob=.3),
                                                               C(id="c", tool="find_charging", prob=.3)])),
        ClarScenario("clear_nav", BeliefState(candidates=[C(id="a", tool="navigate", params={"d": "airport"},
                                                            prob=1.0)])),
    ]


def random_scenarios(n: int, seed: int = 0) -> list[ClarScenario]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        k = rng.randint(1, 5)
        tools = rng.sample(["navigate", "find_cafe", "find_charging", "send_message", "climate", "reminder"],
                           min(k, 3))
        cands = []
        for j in range(k):
            cands.append(Candidate(id=f"c{j}", tool=rng.choice(tools),
                                   params={"x": rng.choice(["a", "b", "c"]), "y": rng.choice(["p", "q"])},
                                   prob=rng.random() ** 2 + 0.01))
        # make ids/param combos unique
        seen, uniq = set(), []
        for c in cands:
            key = (c.tool, c.params["x"], c.params["y"])
            if key not in seen:
                seen.add(key); uniq.append(c)
        out.append(ClarScenario(f"random_{i}", BeliefState(candidates=uniq),
                                {"y"} if rng.random() < 0.3 else set()))
    return out


def run_dialogue(policy, scen: ClarScenario, truth: Candidate, budget: int = 3) -> dict:
    belief, history = scen.belief, ClarificationHistory(budget=budget)
    questions = useful = unnecessary = lookups = 0
    resolvable = set(scen.resolvable)
    for _ in range(10):
        d = policy.decide(belief, history, resolvable_params=frozenset(resolvable))
        if d.kind == DecisionKind.PROCEED:
            chosen = next(c for c in belief.candidates if c.id == d.candidate_id)
            return {"success": chosen.id == truth.id, "questions": questions, "useful": useful,
                    "unnecessary": unnecessary, "lookups": lookups}
        value = _value(truth, d.parameter)
        if d.kind == DecisionKind.GATHER_CONTEXT:
            lookups += 1
            resolvable.discard(d.parameter)
            belief, _ = update_with_answer(belief, d.parameter, value)
            continue
        questions += 1
        top_before = belief.top()
        if top_before.prob >= 0.8:
            unnecessary += 1
        belief, ok = update_with_answer(belief, d.parameter, value)
        history = history.model_copy(update={"asked_params": [*history.asked_params, d.parameter]})
        if belief.top().id != top_before.id or belief.top().prob - top_before.prob > 0.1:
            useful += 1
    chosen = belief.top()
    return {"success": chosen.id == truth.id, "questions": questions, "useful": useful,
            "unnecessary": unnecessary, "lookups": lookups}


def evaluate(scenarios: list[ClarScenario] | None = None, trials: int = 50, seed: int = 1) -> dict[str, dict]:
    scenarios = scenarios or handmade() + random_scenarios(30)
    rng = random.Random(seed)
    results: dict[str, dict] = {}
    for name, factory in ALL_POLICIES.items():
        policy = factory()
        agg = {"success": 0.0, "questions": 0.0, "useful": 0.0, "unnecessary": 0.0, "lookups": 0.0}
        n = 0
        for scen in scenarios:
            for _ in range(trials):
                truth = rng.choices(scen.belief.candidates, weights=[c.prob for c in scen.belief.candidates])[0]
                r = run_dialogue(policy, scen, truth)
                for k in agg:
                    agg[k] += float(r[k])
                n += 1
        results[name] = {k: round(v / n, 3) for k, v in agg.items()}
    return results


def main() -> None:
    res = evaluate()
    print(f"{'policy':<16}{'success':>9}{'questions':>11}{'useful':>8}{'unneeded':>10}{'lookups':>9}")
    for name, r in res.items():
        print(f"{name:<16}{r['success']:>9.3f}{r['questions']:>11.3f}{r['useful']:>8.3f}"
              f"{r['unnecessary']:>10.3f}{r['lookups']:>9.3f}")


if __name__ == "__main__":
    main()
