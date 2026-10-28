import pytest

from module_1_simulator import CarEnvironment, make_state
from module_2_nlu import RuleBasedParser
from module_3_uncertainty import (BeliefBuilder, ContextResolver, apply_temperature, expected_calibration_error,
                                  fit_temperature, goal_of, tool_name)

P = RuleBasedParser()


def build(u, *presets, i=0, **kw):
    env = CarEnvironment(make_state(*presets))
    r = P.parse(u)
    return BeliefBuilder(ContextResolver(env), **kw).build(r.tasks[i], i, r.confidence), env


def ranked(b):
    return [(c.tool, round(c.prob, 2)) for c in b.belief.ranked()]


def test_tea_example_keeps_pdf_probabilities():
    b, _ = build("I need some tea before the meeting.")
    assert ranked(b) == [("find_cafe", 0.55), ("find_rest_area", 0.25), ("reminder", 0.15), ("navigate", 0.05)]
    assert b.report.is_ambiguous


def test_calendar_reference_is_resolved_internally():
    b, env = build("Take me to my next meeting")
    assert b.belief.top().params["destination"] == "tech_park" and b.belief.top().prob == 1.0
    assert any(r.tool == "get_calendar_events" for r in env.log)


def test_meeting_people_split_into_recipient_alternatives():
    b, _ = build("Take me to a charging station near my next appointment, and tell them I may be late.", i=1)
    assert {c.params["recipient"]: round(c.prob, 2) for c in b.belief.candidates} == {"c_priya": 0.55,
                                                                                       "c_rahul_v": 0.45}
    assert b.resolvable_params == set()      # both attend the meeting: must ask
    assert "organizer" in b.labels[b.belief.top().id]["recipient"]


def test_duplicate_first_name_resolvable_from_calendar_when_message_is_about_lateness():
    b, _ = build("Tell Rahul I'm running late")
    assert b.resolvable_params == {"recipient"}
    b2, _ = build("Call Rahul")
    assert b2.resolvable_params == set() and len(b2.belief.candidates) == 2


def test_context_reweighting_hot_prefers_ac():
    b, _ = build("It's getting hot in here")
    assert b.belief.top().tool == "climate" and b.belief.top().prob > 0.8
    b_off, _ = build("It's getting hot in here", use_context_weights=False)
    assert b_off.belief.top().prob < 0.8


def test_low_battery_boosts_charging_stop():
    b, _ = build("Find somewhere to stop", "low_battery")
    assert b.belief.top().tool == "find_charging"
    b2, _ = build("Find somewhere to stop")
    assert b2.belief.top().tool == "find_rest_area"


def test_unknown_request_has_no_belief_and_full_epistemic_uncertainty():
    b, _ = build("blah blah")
    assert b.belief is None and b.report.epistemic == 1.0


def test_missing_parameter_increases_epistemic_uncertainty():
    b, _ = build("Message Rahul")
    assert "text" in b.report.missing_params and b.report.epistemic > 0.1


def test_tool_name_roundtrip():
    assert tool_name("find_poi", {"category": "cafe"}) == "find_cafe"
    assert goal_of("find_cafe") == "find_poi" and goal_of("find_charging") == "find_charging"


def test_temperature_scaling_and_fit():
    assert apply_temperature([0.5, 0.5]) == [0.5, 0.5]
    sharp = apply_temperature([0.6, 0.4], 0.5)
    assert sharp[0] > 0.6
    # data where the top-scored option is always right -> sharpen (T < 1)
    ex = [([0.6, 0.4], 0)] * 20
    assert fit_temperature(ex) < 1.0
    # data where it's right 50% of the time -> flatten (T > 1)
    ex2 = [([0.7, 0.3], 0)] * 10 + [([0.7, 0.3], 1)] * 10
    assert fit_temperature(ex2) > 1.0


def test_ece():
    assert expected_calibration_error([1.0, 1.0], [True, True]) == pytest.approx(0.0)
    assert expected_calibration_error([0.9, 0.9], [False, False]) == pytest.approx(0.9)


def test_recipient_with_possessive_is_resolved():
    from module_1_simulator.environment import CarEnvironment
    from module_3_uncertainty import ContextResolver
    alts = ContextResolver(CarEnvironment()).resolve("recipient", "my landlord")
    assert [a.value for a in alts] == ["c_landlord"]
