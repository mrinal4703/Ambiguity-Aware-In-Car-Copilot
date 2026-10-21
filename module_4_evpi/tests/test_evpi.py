import pytest

from contracts import BeliefState, Candidate, ClarificationHistory
from module_4_evpi.evpi import (
    TOOL_PARAM, answer_options, evpi, make_question, score_all,
    uncertain_parameters, update_with_answer,
)


def tea():
    return BeliefState(candidates=[
        Candidate(id="a", tool="find_tea_shop", prob=0.55),
        Candidate(id="b", tool="find_rest_stop", prob=0.25),
        Candidate(id="c", tool="add_reminder", prob=0.15),
        Candidate(id="d", tool="navigate_known_destination", prob=0.05),
    ])


def two_params():
    # p1: A, A, B   p2: x, y, x
    return BeliefState(candidates=[
        Candidate(id="1", tool="t", params={"p1": "A", "p2": "x"}, prob=0.5),
        Candidate(id="2", tool="t", params={"p1": "A", "p2": "y"}, prob=0.3),
        Candidate(id="3", tool="t", params={"p1": "B", "p2": "x"}, prob=0.2),
    ])


def test_belief_is_normalised():
    b = BeliefState(candidates=[Candidate(id="a", tool="t", prob=2), Candidate(id="b", tool="t", prob=2)])
    assert [c.prob for c in b.candidates] == pytest.approx([0.5, 0.5])


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        BeliefState(candidates=[Candidate(id="a", tool="t", prob=1), Candidate(id="a", tool="t", prob=1)])


def test_evpi_distinct_tools_resolves_everything():
    assert evpi(tea(), TOOL_PARAM) == pytest.approx(0.45)  # 1.0 - 0.55


def test_evpi_partial_split():
    b = two_params()
    assert evpi(b, "p1") == pytest.approx(0.2)   # (0.5 + 0.2) - 0.5
    assert evpi(b, "p2") == pytest.approx(0.3)   # (0.5 + 0.3) - 0.5


def test_certain_parameter_is_not_uncertain():
    b = two_params()
    assert TOOL_PARAM not in uncertain_parameters(b)
    assert evpi(b, TOOL_PARAM) == pytest.approx(0.0)


def test_redundancy_penalty_changes_choice():
    b = two_params()
    fresh = score_all(b, ClarificationHistory(), lam=0.3)
    assert max(fresh, key=fresh.get) == "p2"
    asked = score_all(b, ClarificationHistory(asked_params=["p2"]), lam=0.3)
    assert asked["p2"] == pytest.approx(0.0)
    assert max(asked, key=asked.get) == "p1"


def test_update_matched_renormalises():
    new, ok = update_with_answer(two_params(), "p1", "A")
    assert ok
    assert [c.id for c in new.candidates] == ["1", "2"]
    assert new.top().prob == pytest.approx(0.5 / 0.8)


def test_update_unmatched_leaves_belief_unchanged():
    b = two_params()
    new, ok = update_with_answer(b, "p1", "Z")
    assert not ok and new is b


def test_answer_options_sorted_by_mass():
    opts = answer_options(two_params(), "p1")
    assert opts[0][0] == "A" and opts[0][1] == pytest.approx(0.8)


def test_make_question_templates_and_phraser():
    q = make_question(TOOL_PARAM, ["find_tea_shop", "find_rest_stop"])
    assert q == "What would you like me to do: find tea shop or find rest stop?"
    assert "something else" in make_question("recipient", ["a", "b", "c", "d"])
    assert make_question("recipient", ["a"], phraser=lambda p, o: f"custom {p} {o}") == "custom recipient ['a']"
