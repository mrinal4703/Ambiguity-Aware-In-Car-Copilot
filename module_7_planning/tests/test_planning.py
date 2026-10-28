import pytest

from contracts import SafetyClass, SafetyVerdict, Verdict
from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_7_planning import Executor, Planner, UnsupportedGoal, forward_search
from module_7_planning.actions import A


def actions(plan):
    return [s.action for s in plan.steps]


def test_forward_search_finds_shortest_plan():
    acts = [A("a", add={"x"}), A("b", pre={"x"}, add={"y"}), A("c", pre={"y"}, add={"g"}),
            A("shortcut", pre={"x"}, add={"g"})]
    seq, _ = forward_search(acts, frozenset(), frozenset({"g"}))
    assert [a.name for a in seq] == ["a", "shortcut"]


def test_navigate_plan_and_dependencies():
    plan = Planner().plan("navigate", {"destination": "tech_park"}, CarEnvironment())
    assert actions(plan) == ["get_vehicle_state", "check_range", "calculate_route", "set_navigation"]
    assert plan.steps[3].depends_on == ["s3"]
    assert plan.steps[3].safety_class == SafetyClass.CONSEQUENTIAL


def test_charging_plan_depends_on_navigation_state():
    env = CarEnvironment()
    assert actions(Planner().plan("find_charging", {}, env))[-1] == "set_navigation"
    env.call("set_navigation", destination="esplanade")
    assert actions(Planner().plan("find_charging", {}, env))[-1] == "add_waypoint"


def test_unsupported_goal():
    with pytest.raises(UnsupportedGoal):
        Planner().plan("unsupported", {"feature": "seat_massage"}, CarEnvironment())


def test_low_battery_navigation_replans_with_charging_stop():
    env = CarEnvironment(make_state("low_battery"))
    rep = Executor(env).start("navigate", {"destination": "cuttack"})
    assert rep.succeeded and rep.replans == 1
    assert env.navigation["destination"] == "cuttack" and len(env.navigation["waypoints"]) == 1


def test_station_failure_during_execution_triggers_replan():
    env = CarEnvironment()
    env.call("set_navigation", destination="cuttack")
    first = Executor(CarEnvironment(env.state)).start("find_charging", {}).blackboard[
        "choose_charging_station"]["station_id"]
    env.schedule("add_waypoint", lambda e: e.set_station_availability(first, False))
    rep = Executor(env).start("find_charging", {})
    assert rep.succeeded, rep.message
    assert rep.replans == 1
    assert first in rep.context["exclude_stations"]
    assert env.navigation["waypoints"] and env.navigation["waypoints"][0] != first


def test_message_plan_and_verification():
    env = CarEnvironment()
    rep = Executor(env).start("send_message", {"recipient": "c_priya", "text": "Running late"})
    assert rep.succeeded and env.state["messages_sent"][-1]["to"] == "c_priya"
    assert all(o.verified for o in rep.outcomes)


def test_unresolved_recipient_fails_safely():
    env = CarEnvironment()
    rep = Executor(env).start("send_message", {"recipient": "rahul", "text": "hi"})
    assert rep.status == "failed" and not env.state["messages_sent"]


def test_gate_confirm_then_resume():
    env = CarEnvironment()

    def gate(step, params, env, confirmed):
        if step.safety_class != SafetyClass.LOW and not confirmed:
            return SafetyVerdict(verdict=Verdict.CONFIRM, reason="please confirm", step_id=step.id)
        return None
    ex = Executor(env, gate=gate)
    rep = ex.start("send_message", {"recipient": "c_priya", "text": "late"})
    assert rep.status == "awaiting_confirmation" and rep.pending.action == "send_message"
    assert not env.state["messages_sent"]
    rep = ex.resume(rep, confirmed=True)
    assert rep.succeeded and env.state["messages_sent"]


def test_gate_block_and_cancel():
    env = CarEnvironment()
    ex = Executor(env, gate=lambda s, p, e, c: SafetyVerdict(verdict=Verdict.BLOCK, reason="no"))
    assert ex.start("climate", {"delta_c": -2}).status == "blocked"
    ex2 = Executor(env, gate=lambda s, p, e, c: None if c else SafetyVerdict(verdict=Verdict.CONFIRM, reason="?"))
    rep = ex2.start("windows", {"position": 50})
    assert ex2.resume(rep, confirmed=False).status == "cancelled"
    assert env.vehicle["windows"]["front_left"] == 0


def test_tool_error_aborts_with_message():
    env = CarEnvironment()
    rep = Executor(env).start("climate", {"temperature_c": 35})
    assert rep.status == "failed" and "16-30" in rep.message


def test_retry_on_transient_failure():
    env = CarEnvironment()
    env.fail_next("get_calendar_events", "timeout")
    rep = Executor(env).start("info_calendar", {})
    assert rep.succeeded and len(rep.outcomes) == 1


def test_poi_plan_navigates_to_cafe():
    env = CarEnvironment()
    rep = Executor(env).start("find_poi", {"category": "cafe", "near": "@current_route"})
    assert rep.succeeded
    assert env.navigation["destination"] in {"kiit_square", "tech_park", "jaydev_vihar"}
