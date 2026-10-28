from module_1_simulator import TOOL_SPECS, CarEnvironment, make_state


def env(*p):
    return CarEnvironment(make_state(*p))


def test_reproducible_initial_state():
    assert CarEnvironment().state == CarEnvironment().state
    a, b = CarEnvironment(seed=7, perturb=True), CarEnvironment(seed=7, perturb=True)
    assert a.state == b.state


def test_vehicle_state_and_range():
    e = env()
    r = e.call("get_vehicle_state")
    assert r.ok and r.data["battery_pct"] == 35.0
    assert abs(r.data["range_km"] - 70.0) < 0.1      # 30 kWh * 35% / 0.15


def test_unknown_tool_is_reported_not_faked():
    r = env().call("activate_seat_massage")
    assert not r.ok and "unknown tool" in r.error


def test_missing_parameters():
    r = env().call("send_message", contact_id="c_priya")
    assert not r.ok and "missing" in r.error


def test_calendar_next_event():
    r = env().call("get_calendar_events", next_only=True)
    assert r.ok and r.data[0]["id"] == "ev_review" and r.data[0]["location"] == "tech_park"


def test_contacts_query_two_rahuls():
    r = env().call("get_contacts", query="rahul")
    assert {c["id"] for c in r.data} == {"c_rahul_v", "c_rahul_d"}


def test_charging_search_connector_filter():
    r = env().call("search_charging_stations", near="airport", connector="CCS2")
    assert r.ok and all("CCS2" in s["connectors"] for s in r.data)
    assert "cs_airport" not in [s["id"] for s in r.data]


def test_route_and_navigation():
    e = env()
    r = e.call("calculate_route", destination="airport")
    assert r.ok and r.data["path"][0] == "home" and r.data["path"][-1] == "airport"
    n = e.call("set_navigation", destination="Biju Patnaik Airport")
    assert n.ok and e.navigation["destination"] == "airport"


def test_waypoint_unavailable_station_fails():
    e = env()
    e.call("set_navigation", destination="tech_park")
    r = e.call("add_waypoint", waypoint="cs_oldtown")
    assert not r.ok and "unavailable" in r.error


def test_scheduled_mutation_and_failure_injection():
    e = env()
    e.call("set_navigation", destination="tech_park")
    e.schedule("add_waypoint", lambda en: en.set_station_availability("cs_jaydev", False))
    assert not e.call("add_waypoint", waypoint="cs_jaydev").ok
    e.fail_next("get_vehicle_state", "sensor timeout")
    r = e.call("get_vehicle_state")
    assert not r.ok and r.error == "sensor timeout"
    assert e.call("get_vehicle_state").ok


def test_ac_range_enforced_by_tool():
    e = env()
    assert e.call("control_ac", temperature_c=22).ok
    assert e.vehicle["ac"] == {"on": True, "temperature_c": 22.0, "fan": 2}
    assert e.call("control_ac", delta_c=-2).data["temperature_c"] == 20.0
    assert not e.call("control_ac", temperature_c=5).ok


def test_video_only_when_parked():
    assert not env().call("play_video", title="movie").ok
    assert env("parked").call("play_video", title="movie").ok


def test_missing_feature():
    r = env("no_windows_feature").call("control_windows", position=50)
    assert not r.ok and "feature" in r.error


def test_messages_recorded():
    e = env()
    e.call("send_message", contact_id="c_priya", text="Running late")
    assert e.state["messages_sent"][0]["name"] == "Priya Sharma"


def test_every_tool_has_an_implementation():
    e = env()
    for name in TOOL_SPECS:
        assert hasattr(e, f"_t_{name}"), name
