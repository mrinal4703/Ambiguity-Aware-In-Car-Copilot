def test_deadline_explanation_names_the_real_blocker():
    from module_1_simulator.environment import CarEnvironment
    from module_1_simulator.initial_states import make_state
    from module_6_csp import ChargingPlanner, ChargingProblem
    env = CarEnvironment(make_state("low_battery"))
    res = ChargingPlanner.from_env(env).solve(ChargingProblem.from_env(env, "cuttack", deadline_min=30))
    kiit = next(r for r in res.station_results if r.route_id == "via_cs_kiit")
    assert res.best is None
    assert kiit.violated_constraints == ["deadline"]
