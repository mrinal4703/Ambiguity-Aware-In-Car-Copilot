from module_2_nlu import RuleBasedParser
from module_2_nlu.responder import GroundedResponder, grounding_issues


def goals(u):
    return [[c.goal for c in t.candidates] for t in RuleBasedParser().parse(u).tasks]


def test_tired_is_ambiguous_between_rest_coffee_and_chat():
    assert goals("I am tired") == [["find_poi", "find_poi", "chat"]]


def test_running_late_offers_message_route_and_eta():
    t = RuleBasedParser().parse("I'm running late").tasks[0]
    assert [c.goal for c in t.candidates] == ["send_message", "navigate", "info_eta"]
    assert t.urgency == "high"


def test_destination_change_traffic_eta():
    t = RuleBasedParser().parse("Change my destination to the airport").tasks[0]
    assert t.candidates[0].params["destination"] == "airport" and t.entities["destination_change"]
    assert goals("How is the traffic?") == [["info_traffic"]]
    assert goals("When will we arrive?") == [["info_eta"]]


def test_missing_driver_assistance_features():
    assert RuleBasedParser().parse("Turn on parking assist").tasks[0].candidates[0].params["feature"] == "parking_assist"
    assert RuleBasedParser().parse("Enable lane keeping").tasks[0].candidates[0].params["feature"] == "lane_assist"


def test_toll_preference_soft_unless_strict():
    soft = RuleBasedParser().parse("Take me to Cuttack avoiding tolls").tasks[0].constraints
    hard = RuleBasedParser().parse("Take me to Cuttack, no tolls at all").tasks[0].constraints
    assert soft == {"avoid_tolls": True}
    assert hard["avoid_tolls_strict"]


def test_responder_without_llm_returns_template(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    t = "Navigating to Cuttack: 26.0 km, about 28 min."
    assert GroundedResponder().phrase(t) == t


def test_responder_accepts_faithful_rewrite():
    r = GroundedResponder(complete=lambda s, u: "Heading to Cuttack now: 26.0 km, roughly 28 min.")
    assert r.phrase("Navigating to Cuttack: 26.0 km, about 28 min.").startswith("Heading")


def test_responder_rejects_changed_numbers_names_and_claims():
    t = "Send \"I am running late\" to Priya Sharma?"
    assert grounding_issues(t, "Send \"I am running late\" to Rahul?")
    assert grounding_issues("Navigating to Cuttack: 26.0 km.", "Navigating to Cuttack: 25 km.")
    assert grounding_issues(t, "I've sent Priya Sharma \"I am running late\".")
    r = GroundedResponder(complete=lambda s, u: "Done, message sent to Priya.")
    assert r.phrase(t) == t and r.rejected
