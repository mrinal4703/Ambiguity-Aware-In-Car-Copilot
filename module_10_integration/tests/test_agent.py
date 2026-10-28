from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_10_integration import ABLATIONS, CopilotAgent
from module_10_integration.metrics import run_trial
from module_10_integration.scenarios import SCENARIOS, by_id


def agent(preset="default", config="full_fixed"):
    return CopilotAgent(CarEnvironment(make_state(preset)), ABLATIONS[config])


def test_clear_request_executes_without_questions():
    a = agent()
    t = a.handle("Take me to the airport")
    assert t.kind == "done"
    assert a.env.state["navigation"]["destination"] == "airport"
    assert a.stats["questions"] == 0


def test_ambiguous_tea_asks_then_confirms_then_navigates():
    a = agent()
    t = a.handle("I need tea")
    assert t.kind == "question"
    assert len(t.candidates) >= 2
    t = a.handle("a cafe")
    assert t.kind in ("confirm", "done")
    if t.kind == "confirm":
        t = a.handle("yes")
    assert t.kind == "done"
    assert a.env.state["navigation"]["active"]


def test_stray_yes_with_nothing_pending():
    t = agent().handle("yes")
    assert "nothing waiting" in t.reply.lower()


def test_low_battery_replans_with_charging():
    a = agent("low_battery")
    t = a.handle("Take me to Cuttack")
    assert t.kind == "confirm"
    t = a.handle("yes")
    nav = a.env.state["navigation"]
    assert t.kind == "done" and any(a.env.station(w) for w in nav["waypoints"])


def test_unsafe_requests_are_blocked():
    a = agent()
    t = a.handle("Message my landlord that the rent is late")
    assert t.kind in ("blocked", "refused")
    assert not a.env.state["messages_sent"]
    t = a.handle("Play a movie")
    assert t.kind in ("blocked", "refused")


def test_missing_capability_is_refused_honestly():
    a = agent()
    t = a.handle("Give me a seat massage")
    assert t.kind == "refused"
    assert {r.tool for r in a.env.log} <= {"get_vehicle_state", "get_driving_context"}


def test_full_system_passes_every_scenario():
    failed = [s.id for s in SCENARIOS if not run_trial(s, ABLATIONS["full_fixed"]).success]
    assert failed == []


def test_llm_alone_fabricates():
    r = run_trial(by_id("base_nav_airport"), ABLATIONS["llm_alone"])
    assert not r.success and r.fabricated >= 1


def test_api_roundtrip():
    from fastapi.testclient import TestClient
    from module_10_integration.api import app
    c = TestClient(app)
    assert c.post("/reset", json={"preset": "default", "config": "full_fixed"}).status_code == 200
    r = c.post("/chat", json={"message": "Take me to the airport"}).json()
    assert r["turn"]["kind"] == "done"
    assert r["state"]["snapshot"]["navigation"]["route"]["geometry"]["coordinates"]
    assert len(c.get("/world").json()["locations"]) >= 10
    assert c.get("/scenarios").status_code == 200
    assert c.post("/scenarios/base_nav_airport/run").json()["success"]
    assert c.post("/scenarios/nope/run").status_code == 404
    assert c.post("/chat", json={"message": "  "}).status_code == 400


def test_api_drive_and_events():
    from fastapi.testclient import TestClient
    from module_10_integration.api import app
    c = TestClient(app)
    c.post("/reset", json={"preset": "battery_drain", "config": "full_fixed"})
    c.post("/chat", json={"message": "Navigate to Cuttack"})
    r = c.post("/drive", json={"minutes": 5}).json()
    assert r["turn"]["kind"] == "confirm" and "draining faster" in r["turn"]["reply"]
    assert r["state"]["beliefs"]["consumption_factor"]["mean"] > 1.2
    assert c.post("/event", json={"kind": "nope"}).status_code == 400
    assert c.post("/drive", json={"minutes": 0}).status_code == 400


def test_preferences_learned_from_choices_skip_the_question():
    from module_1_simulator.initial_states import make_state
    agent = CopilotAgent(CarEnvironment(make_state()))
    for _ in range(2):        # one odd choice does not flip it; two consistent ones do
        assert agent.handle("I need tea").kind == "question"
        agent.handle("just add a reminder")
    t = agent.handle("I need tea")
    assert t.kind != "question" and agent.env.state["reminders"]


def test_driving_load_raises_question_cost():
    from module_1_simulator.initial_states import make_state
    hw = CopilotAgent(CarEnvironment(make_state("highway")))
    assert hw.driving_difficulty() == "high" and hw._question_cost() > 0


def test_malformed_events_are_rejected_clearly():
    import pytest
    a = CopilotAgent()
    for kind, kw, msg in [("station_offline", {"station": "nope"}, "unknown station"),
                          ("road_closed", {"a": "home", "b": "nope"}, "no open road"),
                          ("drain", {"factor": 50}, "factor must be"),
                          ("traffic", {"a": "home"}, "needs"),
                          ("flood", {}, "unknown event")]:
        with pytest.raises(ValueError, match=msg):
            a.event(kind, **kw)
    assert a.event("road_closed", a="home", b="kiit_square").kind == "answer"


def test_stop_at_current_destination_is_not_added_twice():
    a = CopilotAgent()
    for u in ["Take me to KIIT Square", "I need tea", "a cafe", "yes"]:
        t = a.handle(u)
    assert t.kind == "done" and "via" not in t.reply and a.env.navigation["waypoints"] == []
