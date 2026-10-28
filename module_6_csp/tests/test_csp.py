import pytest

from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_6_csp import CSP, ChargingPlanner, ChargingProblem, charge_minutes, check_direct


def test_generic_csp_map_colouring():
    csp = CSP(["a", "b", "c"], {v: ["r", "g", "b"] for v in "abc"})
    for x, y in [("a", "b"), ("b", "c"), ("a", "c")]:
        csp.add(f"{x}!={y}", (x, y), lambda p, q: p != q)
    sols, stats, _ = csp.solve()
    assert len(sols) == 6
    assert all(len(set(s.values())) == 3 for s in sols)


def test_forward_checking_reduces_nodes():
    csp = CSP([f"q{i}" for i in range(6)], {f"q{i}": list(range(6)) for i in range(6)})
    for i in range(6):
        for j in range(i + 1, 6):
            csp.add(f"q{i}q{j}", (f"q{i}", f"q{j}"), lambda a, b, d=j - i: a != b and abs(a - b) != d)
    plain, s_plain, _ = csp.solve(forward_checking=False, mrv=False)
    fc, s_fc, _ = csp.solve(forward_checking=True, mrv=True)
    assert len(plain) == len(fc) == 4
    assert s_fc.nodes < s_plain.nodes


def test_charge_minutes_tapers_above_80():
    st = {"power_kw": 60}
    assert charge_minutes(st, 30, 20, 80) == pytest.approx(60 / 100 * 30 / 54 * 60)
    assert charge_minutes(st, 30, 80, 100) > charge_minutes(st, 30, 60, 80)
    assert charge_minutes(st, 30, 50, 40) == 0


@pytest.fixture
def low():
    return CarEnvironment(make_state("low_battery"))


def solve(env, dest="tech_park", deadline=None, **kw):
    return ChargingPlanner.from_env(env).solve(ChargingProblem.from_env(env, dest, deadline, **kw))


def test_low_battery_plan_respects_hard_constraints(low):
    r = solve(low)
    assert r.feasible
    for s in r.solutions:
        assert "CCS2" in s.station["connectors"] and s.station["available"]
        assert s.arrival_pct >= 10 and s.final_pct >= 10
    ids = {s.station["id"] for s in r.solutions}
    assert "cs_airport" not in ids and "cs_khandagiri" not in ids and "cs_oldtown" not in ids
    assert r.best.target_pct == 80


def test_infeasible_explanations(low):
    res = {f.route_id: f for f in solve(low).station_results}
    assert res["via_cs_airport"].violated_constraints == ["connector"]
    assert "available" in res["via_cs_oldtown"].violated_constraints
    assert "connector" in res["via_cs_khandagiri"].violated_constraints
    assert "reach_station" in res["via_cs_cuttack"].violated_constraints


def test_deadline_can_make_problem_infeasible(low):
    r = solve(low, deadline=20)
    assert not r.feasible
    assert "deadline" in r.explanation
    assert solve(low, deadline=40).feasible
    assert all(s.total_min <= 40 for s in solve(low, deadline=40).solutions)


def test_critical_battery_cannot_reach_any_station():
    r = solve(CarEnvironment(make_state("critical_battery")))
    assert not r.feasible
    assert all(not f.feasible for f in r.station_results)


def test_exclusion_supports_replanning():
    low = CarEnvironment()
    first = solve(low).best.station["id"]
    second = solve(low, exclude=(first,))
    assert second.feasible and second.best.station["id"] != first
    low.set_station_availability(first, False)
    assert solve(low).best.station["id"] != first


def test_missing_feature_blocks_everything(low):
    low.vehicle["features"].remove("charging_search")
    r = solve(low)
    assert not r.feasible
    assert all("tools_available" in f.violated_constraints for f in r.station_results)


def test_preferred_network_is_soft():
    env = CarEnvironment()
    def rank(r):
        return [s.station["network"] for s in r.ranked_options(5)].index("Statiq")
    plain, pref = solve(env), solve(env, preferred_network="Statiq")
    assert pref.feasible and rank(pref) < rank(plain)
    assert pref.best.station["id"] == plain.best.station["id"]   # soft: does not override a much better option


def test_avoid_tolls(low):
    r = solve(low, dest="cuttack", avoid_tolls=True)
    for s in r.solutions:
        assert s.preference in ("no_toll", "fastest", "shortest", "eco")


def test_no_destination(low):
    r = solve(low, dest=None)
    assert r.feasible and r.best.option.waypoints == [r.best.station["id"]]


def test_direct_route_check():
    assert check_direct(CarEnvironment(), "tech_park").feasible
    f = check_direct(CarEnvironment(make_state("low_battery")), "cuttack")
    assert not f.feasible and f.violated_constraints == ["reach_destination"]
    assert not check_direct(CarEnvironment(), "tech_park", deadline_min=1).feasible
