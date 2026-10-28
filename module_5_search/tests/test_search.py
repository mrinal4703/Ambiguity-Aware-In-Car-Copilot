import itertools

import pytest

from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_5_search import CostWeights, RoadGraph, RouteSolver, astar, make_router, uniform_cost_search
from module_5_search.compare import compare


@pytest.fixture
def env():
    return CarEnvironment()


def test_graph_built_from_env(env):
    g = RoadGraph.from_env(env)
    assert set(g.nodes()) == set(env.state["locations"])
    assert all(e.distance_km > 0 for es in g.adj.values() for e in es)


def test_ucs_matches_environment_dijkstra(env):
    g = RoadGraph.from_env(env)
    r = uniform_cost_search(g, "home", "tech_park")
    assert r.path == env.call("calculate_route", destination="tech_park").data["path"]


def test_heuristic_is_admissible(env):
    g = RoadGraph.from_env(env)
    for pref in [CostWeights(time=1), CostWeights(time=0, distance=1), CostWeights(time=0, energy=1)]:
        for goal in g.nodes():
            h = g.heuristic(pref, goal)
            for n in g.nodes():
                true = uniform_cost_search(g, n, goal, pref).cost
                assert h(n) <= true + 1e-9


def test_astar_optimal_and_expands_fewer_nodes(env):
    res = compare(env)
    for r in res.values():
        assert r["same_optimal_cost"] == 1.0
        assert r["astar_expanded"] <= r["ucs_expanded"]
    assert res["fastest"]["astar_expanded"] < res["fastest"]["ucs_expanded"]


def test_no_toll_avoids_tolls(env):
    s = RouteSolver.from_env(env)
    tolled = [(e_from, e.to) for e_from, es in s.graph.adj.items() for e in es if e.toll]
    assert tolled, "world should contain toll roads"
    for o, d in itertools.permutations(s.graph.nodes(), 2):
        r = s.route(o, d, preference="no_toll")
        if r:
            assert not r.toll


def test_route_with_waypoint(env):
    s = RouteSolver.from_env(env)
    r = s.route("home", "tech_park", ["kiit_square"])
    assert r.path[0] == "home" and "kiit_square" in r.path and r.path[-1] == "tech_park"
    assert len(r.legs) == 2


def test_alternatives_are_distinct_and_sorted(env):
    alts = RouteSolver.from_env(env).alternatives("home", "airport", k=3)
    assert len(alts) == 3
    assert len({tuple(a.path) for a in alts}) == 3
    assert [a.cost for a in alts] == sorted(a.cost for a in alts)


def test_charging_routes(env):
    opts = RouteSolver.from_env(env).charging_routes("home", "tech_park", env.state["stations"])
    assert len(opts) == len(env.state["stations"])
    best = opts[0]
    assert best.metadata["station_id"] == "cs_techpark"
    assert best.metadata["leg1_km"] + best.metadata["leg2_km"] == pytest.approx(best.distance_km, abs=0.02)


def test_router_plugs_into_environment():
    env = CarEnvironment(router=make_router("astar"))
    data = env.call("calculate_route", destination="airport", preference="shortest").data
    assert data["path"][0] == "home" and data["path"][-1] == "airport"
    assert "nodes_expanded" in data
    nav = env.call("set_navigation", destination="esplanade")
    assert nav.ok


def test_traffic_changes_time_costs():
    calm = RouteSolver.from_env(CarEnvironment(make_state("default")))
    st = make_state("default")
    st["driving"]["traffic"] = "heavy"
    busy = RouteSolver.from_env(CarEnvironment(st))
    assert busy.route("home", "esplanade").time_min > calm.route("home", "esplanade").time_min


def test_astar_direct(env):
    g = RoadGraph.from_env(env)
    r = astar(g, "home", "home")
    assert r.path == ["home"] and r.cost == 0
