import pytest

from contracts import BeliefState, Candidate, ClarificationHistory, DecisionKind
from module_4_evpi import (AlwaysClarify, AlwaysExecute, EVPIClarifier, FixedThreshold, default_utility, evpi,
                           make_question, match_answer, update_with_noisy_answer, utility_evpi)
from module_4_evpi.evaluate import evaluate, handmade

TEA = BeliefState(candidates=[Candidate(id="a", tool="find_cafe", prob=.55),
                              Candidate(id="b", tool="find_rest_area", prob=.25),
                              Candidate(id="c", tool="reminder", prob=.15),
                              Candidate(id="d", tool="navigate", prob=.05)])
LATE = BeliefState(candidates=[Candidate(id="a", tool="send_message", params={"recipient": "c_priya"}, prob=.55),
                               Candidate(id="b", tool="send_message", params={"recipient": "c_rahul_v"}, prob=.45)])


@pytest.mark.parametrize("reply,expected", [
    ("the first one", "c_priya"), ("second", "c_rahul_v"), ("Priya", "c_priya"),
    ("rahul please", "c_rahul_v"), ("Rahul Verma", "c_rahul_v"), ("nobody", None),
])
def test_match_answer(reply, expected):
    assert match_answer(reply, ["c_priya", "c_rahul_v"], ["Priya Sharma (organizer)", "Rahul Verma (colleague)"]) \
        == expected


def test_match_tool_answer():
    opts = ["find_cafe", "find_rest_area", "reminder"]
    labels = ["find a tea/coffee shop", "find a rest stop", "add a reminder"]
    assert match_answer("a tea shop", opts, labels) == "find_cafe"
    assert match_answer("just remind me", opts, labels) == "reminder"


def test_labeler_used_in_question():
    lab = {"c_priya": "Priya Sharma (organizer)", "c_rahul_v": "Rahul Verma (colleague)"}
    d = EVPIClarifier().decide(LATE, ClarificationHistory(), labeler=lambda p, v: lab.get(v, str(v)))
    assert d.kind == DecisionKind.ASK
    assert d.question == "Which recipient do you mean: Priya Sharma (organizer) or Rahul Verma (colleague)?"


def test_noisy_answer_keeps_alternatives():
    b, ok = update_with_noisy_answer(LATE, "recipient", "c_rahul_v", reliability=0.9)
    assert ok and len(b.candidates) == 2
    assert b.top().params["recipient"] == "c_rahul_v"
    assert b.top().prob == pytest.approx(0.45 * 0.9 / (0.45 * 0.9 + 0.55 * 0.1))


def test_utility_evpi_reduces_to_probability_gain_when_wrong_costs_nothing():
    for p in ["tool"]:
        assert utility_evpi(TEA, p, default_utility(0.0)) == pytest.approx(evpi(TEA, p))


def test_utility_evpi_larger_when_mistakes_are_costly():
    assert utility_evpi(LATE, "recipient", default_utility(-1.0)) > evpi(LATE, "recipient")


def test_baselines():
    h = ClarificationHistory()
    assert AlwaysExecute().decide(TEA, h).kind == DecisionKind.PROCEED
    assert AlwaysClarify().decide(TEA, h).kind == DecisionKind.ASK
    assert FixedThreshold(0.5).decide(TEA, h).kind == DecisionKind.PROCEED
    assert FixedThreshold(0.8).decide(TEA, h).kind == DecisionKind.ASK


def test_evaluation_evpi_asks_fewer_questions_than_always_clarify():
    r = evaluate(handmade(), trials=40)
    assert r["evpi"]["questions"] < r["always_clarify"]["questions"]
    assert r["evpi"]["success"] >= r["always_execute"]["success"]
    assert r["evpi"]["unnecessary"] == 0


def test_make_question_default_wording_unchanged():
    assert make_question("tool", ["find_tea_shop", "find_rest_stop"]) == \
        "What would you like me to do: find tea shop or find rest stop?"
