from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_2_nlu import RuleBasedParser
from module_3_uncertainty import (BatteryBelief, BeliefBuilder, ContextResolver, PreferenceModel, StationBelief,
                                  WorldBelief)


def test_station_belief_updates_with_observations():
    b = StationBelief(5, 0.5)
    p0 = b.p_available
    b.observe(False, 3.0)
    assert b.p_available < p0


def test_battery_belief_learns_faster_drain():
    b = BatteryBelief()
    for _ in range(3):
        b.observe(expected_kwh=1.0, actual_kwh=1.8)
    assert b.mean > 1.5 and b.sd < 0.1
    assert b.p_reach(model_energy_kwh=3.0, usable_kwh=4.0) < 0.2   # 3 x 1.8 = 5.4 > 4


def test_world_belief_summary_and_traffic_update():
    env = CarEnvironment(make_state())
    env.call("set_navigation", destination="cuttack")
    wb = WorldBelief(env)
    assert wb.availability()["cs_oldtown"] < 0.2 < wb.availability()["cs_kiit"]
    path = env.navigation["route"]["path"]
    env.set_road_delay(path[0], path[1], 2.0)
    before = wb.summary()["route_time_min"]["mean"]
    wb.observe_traffic(env.call("get_traffic").data)
    assert wb.summary()["route_time_min"]["mean"] > before
    assert 0.0 <= wb.summary()["p_reach_destination"] <= 1.0


def test_conflicting_calendar_gives_two_destinations():
    env = CarEnvironment(make_state("conflicting_calendar"))
    alts = ContextResolver(env).resolve("destination", "@next_event_location")
    assert {a.value for a in alts} == {"tech_park", "old_town"}


def test_preferences_shift_the_prior_after_repeated_choices():
    env = CarEnvironment(make_state())
    task = RuleBasedParser().parse("I need tea").tasks[0]
    prefs = PreferenceModel()
    base = BeliefBuilder(ContextResolver(env)).build(task).belief.top().prob
    for _ in range(3):
        prefs.record("I need tea", "find_cafe")
    learned = BeliefBuilder(ContextResolver(env), preferences=prefs).build(task).belief
    assert learned.top().tool == "find_cafe" and learned.top().prob > base
