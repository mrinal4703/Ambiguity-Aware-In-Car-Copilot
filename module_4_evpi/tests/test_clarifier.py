import pytest

from contracts import BeliefState, Candidate, DecisionKind
from module_4_evpi import ClarifierConfig, EVPIClarifier, belief_features
from module_4_evpi.tests.test_evpi import tea, two_params


def test_proceeds_when_confident():
    b = BeliefState(candidates=[Candidate(id="a", tool="t", prob=0.9), Candidate(id="b", tool="u", prob=0.1)])
    clar = EVPIClarifier()
    d = clar.decide(b, clar.new_history())
    assert d.kind == DecisionKind.PROCEED and d.candidate_id == "a"


def test_asks_when_ambiguous():
    clar = EVPIClarifier()
    d = clar.decide(tea(), clar.new_history())
    assert d.kind == DecisionKind.ASK and d.parameter == "tool"
    assert d.question and len(d.options) == 4


def test_gathers_context_before_asking():
    clar = EVPIClarifier()
    d = clar.decide(two_params(), clar.new_history(), resolvable_params={"p1"})
    assert d.kind == DecisionKind.GATHER_CONTEXT and d.parameter == "p1"


def test_context_does_not_use_budget():
    clar = EVPIClarifier()
    b, ok = clar.apply_context(two_params(), "p1", "A")
    assert ok and clar.new_history().remaining == 3


def test_budget_exhausted_proceeds_with_top():
    clar = EVPIClarifier(ClarifierConfig(budget=1))
    h = clar.new_history()
    b, h, _ = clar.apply_answer(two_params(), h, "p1", "A")   # still ambiguous on p2
    d = clar.decide(b, h)
    assert d.kind == DecisionKind.PROCEED and d.budget_exhausted


def test_min_score_stops_low_value_questions():
    clar = EVPIClarifier(ClarifierConfig(min_score=0.5))
    d = clar.decide(two_params(), clar.new_history())
    assert d.kind == DecisionKind.PROCEED and "min_score" in d.reason


def test_full_dialogue_terminates_within_budget():
    clar = EVPIClarifier()
    belief, history = tea(), clar.new_history()
    for _ in range(clar.config.budget + 1):
        d = clar.decide(belief, history)
        if d.kind == DecisionKind.PROCEED:
            break
        belief, history, ok = clar.apply_answer(belief, history, d.parameter, "find_tea_shop")
        assert ok
    assert d.kind == DecisionKind.PROCEED and d.candidate_id == "a"
    assert history.questions_asked == 1


def test_features_for_rl():
    clar = EVPIClarifier()
    f = belief_features(tea(), clar.new_history())
    assert f["top_prob"] == pytest.approx(0.55)
    assert f["margin"] == pytest.approx(0.30)
    assert f["n_candidates"] == 4 and f["budget_remaining"] == 3
