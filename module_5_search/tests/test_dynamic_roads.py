from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state
from module_5_search import CostWeights, RoadGraph, astar
from module_5_search import uniform_cost_search as uniform_cost


def _first_leg(env, a, b):
    g = RoadGraph.from_env(env)
    return g, astar(g, a, b, CostWeights())


def test_closed_road_is_avoided_and_astar_still_optimal():
    env = CarEnvironment(make_state())
    g, r = _first_leg(env, "home", "cuttack")
    assert r.found and len(r.path) >= 2
    env.close_road(r.path[0], r.path[1])
    g2 = RoadGraph.from_env(env)
    r2 = astar(g2, "home", "cuttack", CostWeights())
    u2 = uniform_cost(g2, "home", "cuttack", CostWeights())
    assert r2.path[:2] != r.path[:2]
    assert abs(r2.cost - u2.cost) < 1e-6 and r2.cost >= r.cost


def test_delay_raises_route_time():
    env = CarEnvironment(make_state())
    g, r = _first_leg(env, "home", "cuttack")
    env.set_road_delay(r.path[0], r.path[1], 3.0)
    r2 = astar(RoadGraph.from_env(env), "home", "cuttack", CostWeights())
    assert r2.cost > r.cost
