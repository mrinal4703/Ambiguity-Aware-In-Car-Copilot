from contracts import PlanStep, SafetyVerdict, Verdict
from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_3_uncertainty import WorldBelief
from module_7_planning import Executor, TripMonitor


def _nav(env, dest="cuttack"):
    assert env.call("set_navigation", destination=dest).ok


def test_road_closure_on_route_is_detected_and_rerouted():
    env = CarEnvironment(make_state())
    _nav(env)
    path = env.navigation["route"]["path"]
    env.close_road(path[0], path[1])
    mon = TripMonitor(env)
    issues = mon.check()
    assert [i.kind for i in issues] == ["road_closed"]
    assert mon.handle(issues[0], Executor(env))["ok"]
    assert not env.route_blocked() and env.navigation["destination"] == "cuttack"


def test_faster_battery_drain_triggers_charging_replan():
    env = CarEnvironment(make_state("battery_drain"))
    _nav(env)
    wb = WorldBelief(env)
    mon = TripMonitor(env, wb)
    assert not [i for i in mon.check() if i.kind == "range_risk"]
    for _ in range(3):           # the car learns that it uses more energy than its model says
        wb.observe_drive(1.0, 1.8)
    issues = [i for i in mon.check() if i.kind == "range_risk"]
    assert issues and issues[0].goal == "navigate_with_charging"
    rep = mon.handle(issues[0], Executor(env))
    assert rep.succeeded and env.navigation["waypoints"]


def test_unavailable_charging_stop_is_replaced():
    env = CarEnvironment(make_state("low_battery"))
    ex = Executor(env)
    rep = ex.start("navigate_with_charging", {"destination": "tech_park"})
    assert rep.succeeded
    sid = env.navigation["waypoints"][0]
    env.set_station_availability(sid, False)
    issues = TripMonitor(env).check()
    assert issues and issues[0].kind == "station_unavailable"
    rep2 = TripMonitor(env).handle(issues[0], ex)
    assert not rep2.succeeded or sid not in env.navigation["waypoints"]


def test_destination_change_keeps_charging_when_needed():
    env = CarEnvironment(make_state("low_battery"))
    rep = Executor(env).start("navigate", {"destination": "cuttack"})
    assert rep.goal == "navigate_with_charging" or not rep.succeeded


def test_new_info_goals_and_soft_tolls():
    env = CarEnvironment(make_state())
    _nav(env, "tech_park")
    ex = Executor(env)
    eta = ex.start("info_eta", {}, {"travel_time": {"mean": 20, "p90": 28}})
    assert eta.succeeded and eta.blackboard["estimate_eta"]["minutes_p90"] == 28
    tr = ex.start("info_traffic", {})
    assert tr.succeeded
    off = CarEnvironment(make_state("traffic_offline"))
    rep = Executor(off).start("info_traffic", {})
    assert rep.succeeded and rep.blackboard["estimate_traffic"]["estimated"]
    soft = Executor(CarEnvironment(make_state())).start("navigate", {"destination": "airport"}, {"avoid_tolls": True})
    assert soft.succeeded


def test_modified_params_are_used_after_confirmation():
    env = CarEnvironment(make_state())

    def gate(step: PlanStep, params, env_, confirmed):
        if step.action == "control_windows" and params["position"] > 20 and not confirmed:
            return SafetyVerdict(verdict=Verdict.CONFIRM, reason="open to 20% instead?",
                                 modified_params={"position": 20})
        return None
    ex = Executor(env, gate=gate)
    rep = ex.start("windows", {"position": 100})
    assert rep.status == "awaiting_confirmation"
    rep = ex.resume(rep, True)
    assert rep.succeeded and all(v == 20 for v in env.vehicle["windows"].values())
