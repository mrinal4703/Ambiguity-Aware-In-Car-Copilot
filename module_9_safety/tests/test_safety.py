import pytest

from contracts import Verdict
from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_7_planning import Executor, Planner
from module_9_safety import SafetyContext, SafetyPolicy, check_request, verify_outcome

P = SafetyPolicy()


def v(action, params, env=None, **ctx):
    return P.check(action, params, env or CarEnvironment(), SafetyContext(**ctx)).verdict


def test_unknown_tool_and_missing_feature_blocked():
    assert v("open_sunroof", {}) == Verdict.BLOCK
    env = CarEnvironment(make_state("no_windows_feature"))
    assert v("control_windows", {"position": 20}, env, explicit=True) == Verdict.BLOCK


def test_missing_or_unresolved_parameters_deferred():
    assert v("send_message", {"contact_id": "c_priya"}) == Verdict.DEFER
    assert v("set_navigation", {"destination": "@next_event_location"}) == Verdict.DEFER


@pytest.mark.parametrize("params,expected", [({"temperature_c": 35}, Verdict.CONFIRM),   # modify -> 30 C
                                             ({"temperature_c": 15}, Verdict.CONFIRM),   # modify -> 16 C
                                             ({"delta_c": -2}, Verdict.ALLOW),
                                             ({"temperature_c": 22}, Verdict.ALLOW)])
def test_ac_range(params, expected):
    assert v("control_ac", params) == expected


def test_windows_at_highway_speed():
    hw = CarEnvironment(make_state("highway"))
    r = P.check("control_windows", {"position": 80}, hw, SafetyContext(explicit=True))
    assert r.verdict == Verdict.CONFIRM and r.modified_params == {"position": 20}
    assert v("control_windows", {"position": 50}, hw, explicit=True) == Verdict.CONFIRM
    assert v("control_windows", {"position": 20}, hw, explicit=True) == Verdict.ALLOW
    assert v("control_windows", {"position": 80}, explicit=True) == Verdict.ALLOW     # city speed


def test_video_only_when_parked():
    assert v("play_video", {"title": "x"}, explicit=True) == Verdict.BLOCK
    assert v("play_video", {"title": "x"}, CarEnvironment(make_state("parked")), explicit=True) == Verdict.ALLOW


def test_messaging_authorization_and_confidence():
    assert v("send_message", {"contact_id": "c_landlord", "text": "hi"}, confirmed=True) == Verdict.BLOCK
    assert v("send_message", {"contact_id": "c_priya", "text": "hi"}, recipient_confidence=0.6,
             confirmed=True) == Verdict.BLOCK
    assert v("send_message", {"contact_id": "c_priya", "text": "hi"}, recipient_confidence=0.95) == Verdict.CONFIRM
    assert v("send_message", {"contact_id": "c_priya", "text": "hi"}, recipient_confidence=0.95,
             confirmed=True) == Verdict.ALLOW


def test_messages_always_need_confirmation_even_if_explicit():
    assert v("send_message", {"contact_id": "c_priya", "text": "hi"}, explicit=True) == Verdict.CONFIRM


def test_high_workload_defers_non_urgent_comms():
    storm = CarEnvironment(make_state("storm"))
    assert v("make_call", {"contact_id": "c_mom"}, storm, confirmed=True) == Verdict.DEFER
    assert v("make_call", {"contact_id": "c_mom"}, storm, confirmed=True, urgency="high") == Verdict.ALLOW


def test_navigation_confirmation_depends_on_explicitness():
    assert v("set_navigation", {"destination": "airport"}, explicit=True) == Verdict.ALLOW
    assert v("set_navigation", {"destination": "airport"}) == Verdict.CONFIRM
    assert v("add_waypoint", {"waypoint": "cs_kiit"}, confirmed=True) == Verdict.ALLOW


def test_low_risk_tools_allowed():
    assert v("get_vehicle_state", {}) == Verdict.ALLOW
    assert v("choose_charging_station", {}) == Verdict.ALLOW


def test_capability_checker():
    env = CarEnvironment()
    r = check_request("unsupported", {"feature": "seat_massage"}, env)
    assert not r.supported and "seat massage" in r.reason and r.alternative
    assert check_request("navigate", {}, env).supported
    assert not check_request("windows", {}, CarEnvironment(make_state("no_windows_feature"))).supported


def test_gate_with_executor_confirms_message():
    env = CarEnvironment()
    ex = Executor(env, gate=P.gate(SafetyContext(recipient_confidence=1.0)))
    rep = ex.start("send_message", {"recipient": "c_priya", "text": "late"})
    assert rep.status == "awaiting_confirmation" and "Priya" in rep.message
    assert ex.resume(rep).succeeded


def test_check_plan_static():
    env = CarEnvironment()
    plan = Planner().plan("find_charging", {}, env)
    verdicts = P.check_plan(plan, env)
    assert verdicts[-1].verdict == Verdict.CONFIRM          # set_navigation to inferred station


def test_verify_outcome():
    env = CarEnvironment()
    r = env.call("set_navigation", destination="airport")
    assert verify_outcome("set_navigation", {"destination": "airport"}, r, env)[0]
    assert not verify_outcome("set_navigation", {"destination": "cuttack"}, r, env)[0]
    bad = env.call("control_ac", temperature_c=40)
    assert not verify_outcome("control_ac", {"temperature_c": 40}, bad, env)[0]


def test_system_added_waypoints_need_confirmation():
    assert v("set_navigation", {"destination": "cuttack", "waypoints": ["cs_kiit"]}, explicit=True) == Verdict.CONFIRM


def test_ac_modify_suggests_closest_supported_value():
    r = P.check("control_ac", {"temperature_c": 35}, CarEnvironment(), SafetyContext(explicit=True))
    assert r.modified_params["temperature_c"] == 30


def test_windows_modify_is_applied_after_confirmation():
    hw = CarEnvironment(make_state("highway"))
    ex = Executor(hw, gate=P.gate(SafetyContext(explicit=True)))
    rep = ex.start("windows", {"position": 100})
    assert rep.status == "awaiting_confirmation" and "20%" in rep.message
    rep = ex.resume(rep, True)
    assert rep.succeeded and max(hw.vehicle["windows"].values()) == 20


def test_honest_capability_alternatives():
    env = CarEnvironment(make_state("traffic_offline"))
    r = P.check("get_traffic", {}, env)
    assert r.verdict == Verdict.BLOCK and "estimate" in r.reason
    for f in ("parking_assist", "lane_assist"):
        c = check_request("unsupported", {"feature": f}, CarEnvironment())
        assert not c.supported and c.alternative


def test_confirmation_never_unlocks_an_unsafe_value():
    hw = CarEnvironment(make_state("highway"))
    assert v("control_windows", {"position": 80}, hw, confirmed=True) == Verdict.DEFER
    assert v("control_ac", {"temperature_c": 35}, confirmed=True) == Verdict.BLOCK
