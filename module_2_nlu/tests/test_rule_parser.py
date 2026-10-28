import json

import pytest

from module_2_nlu import LLMParser, RuleBasedParser, classify_confirmation, split_tasks, validate_result

P = RuleBasedParser()


def goals(u):
    return [[(c.goal, c.params) for c in t.candidates] for t in P.parse(u).tasks]


def test_multi_task_split_end_to_end_example():
    r = P.parse("Take me to a charging station near my next appointment, and tell them I may be late.")
    assert [t.intent for t in r.tasks] == ["find_charging", "send_message"]
    assert r.tasks[0].candidates[0].params["near"] == "@next_event_location"
    assert r.tasks[1].candidates[0].params == {"recipient": "@next_event_people", "text": "I may be late"}


def test_tea_example_matches_pdf_priors():
    t = P.parse("I need some tea before the meeting.").tasks[0]
    assert [round(c.score, 2) for c in t.candidates] == [0.55, 0.25, 0.15, 0.05]
    assert t.requires_context


@pytest.mark.parametrize("u,goal,params", [
    ("Take me to the airport", "navigate", {"destination": "airport"}),
    ("Navigate to KIIT Square", "navigate", {"destination": "kiit_square"}),
    ("Take me to my next meeting", "navigate", {"destination": "@next_event_location"}),
    ("Set the temperature to 22", "climate", {"on": True, "temperature_c": 22.0}),
    ("Make it 2 degrees colder", "climate", {"on": True, "delta_c": -2.0}),
    ("Open all the windows fully", "windows", {"position": 100}),
    ("Close the windows", "windows", {"position": 0}),
    ("Turn on the seat massage", "unsupported", {"feature": "seat_massage"}),
    ("Turn on autopilot", "unsupported", {"feature": "autopilot"}),
    ("Call mom", "call_contact", {"recipient": "mom"}),
    ("Remind me to buy milk at 5 pm", "reminder", {"text": "Buy milk", "time": "17:00"}),
    ("Tell Priya I'm running late", "send_message", {"recipient": "priya", "text": "I am running late"}),
])
def test_single_goal(u, goal, params):
    g = goals(u)
    assert g == [[(goal, params)]]


def test_relative_values_stay_relative():
    assert goals("Make it 2 degrees colder")[0][0][1]["delta_c"] == -2.0


def test_indirect_hot_has_two_candidates():
    t = P.parse("It's getting hot in here").tasks[0]
    assert [c.goal for c in t.candidates] == ["climate", "windows"] and not t.explicit_action


def test_unknown_gives_no_candidates_and_low_confidence():
    r = P.parse("blah blah")
    assert r.tasks[0].candidates == [] and r.confidence < 0.2


def test_missing_text_reported():
    t = P.parse("Message Rahul").tasks[0]
    assert t.missing_params == ["text"]


def test_split_does_not_break_single_clause():
    assert len(split_tasks("Take me to the airport")) == 1


def test_confirmation_classifier():
    assert classify_confirmation("Yes please") is True
    assert classify_confirmation("no, cancel that") is False
    assert classify_confirmation("take me home") is None


def test_validation_of_rule_output():
    for u in ["Take me home", "Find somewhere to stop", "I'm running low on battery"]:
        assert validate_result(P.parse(u)) == []


def test_llm_parser_accepts_valid_json_in_fences():
    payload = {"tasks": [{"text": "x", "rewritten": "navigate(airport)", "intent": "navigate",
                          "candidates": [{"goal": "navigate", "params": {"destination": "airport"}, "score": 0.9}]}],
               "confidence": 0.9}
    r = LLMParser(complete=lambda s, u: "```json\n" + json.dumps(payload) + "\n```").parse("go to the airport")
    assert r.parser == "llm" and r.tasks[0].candidates[0].params["destination"] == "airport"


def test_llm_parser_falls_back_on_invalid_goal():
    payload = {"tasks": [{"text": "x", "rewritten": "x", "intent": "x",
                          "candidates": [{"goal": "launch_rocket", "params": {}, "score": 1}]}]}
    r = LLMParser(complete=lambda s, u: json.dumps(payload)).parse("Take me to the airport")
    assert r.parser == "rules" and r.notes and r.tasks[0].candidates[0].goal == "navigate"


def test_llm_parser_falls_back_on_exception():
    def boom(s, u):
        raise RuntimeError("network down")
    r = LLMParser(complete=boom).parse("Call mom")
    assert r.parser == "rules" and "RuntimeError" in r.notes[0]


def test_relative_climate_without_number():
    from module_2_nlu import RuleBasedParser
    c = RuleBasedParser().parse("make it cooler").tasks[0].candidates[0]
    assert c.goal == "climate" and c.params["delta_c"] == -2.0


def test_avoiding_tolls_constraint_and_evening_time():
    from module_2_nlu import RuleBasedParser
    p = RuleBasedParser()
    assert p.parse("navigate to the airport avoiding tolls").tasks[0].constraints["avoid_tolls"] is True
    assert p.parse("remind me to buy milk at 6").tasks[0].candidates[0].params["time"] == "18:00"


def test_comma_separated_multi_task():
    from module_2_nlu import RuleBasedParser
    r = RuleBasedParser().parse("Take me to my meeting, find a charger on the way and tell them I am running late")
    assert [t.intent for t in r.tasks] == ["navigate", "find_charging", "send_message"]
