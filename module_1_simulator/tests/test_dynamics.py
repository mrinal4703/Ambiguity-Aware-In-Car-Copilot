from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import make_state


def test_drive_moves_car_and_drains_battery():
    env = CarEnvironment(make_state())
    env.call("set_navigation", destination="airport")
    start_pct, start_time = env.vehicle["battery_pct"], env.driving["time"]
    out = env.drive(60)
    assert "arrived at Biju Patnaik International Airport" in " ".join(out["events"]) or out["moved_km"] > 0
    assert env.vehicle["battery_pct"] < start_pct
    assert env.driving["time"] != start_time


def test_actual_consumption_drains_faster_than_model():
    a, b = CarEnvironment(make_state()), CarEnvironment(make_state("battery_drain"))
    drop = []
    for e in (a, b):
        start = e.vehicle["battery_pct"]
        e.call("set_navigation", destination="airport")
        e.drive(60)
        drop.append(start - e.vehicle["battery_pct"])
    assert drop[1] > 1.5 * drop[0]


def test_closed_road_is_avoided_and_reported():
    env = CarEnvironment(make_state())
    env.call("set_navigation", destination="cuttack")
    path = env.navigation["route"]["path"]
    a, b = path[1], path[2]
    env.close_road(a, b)
    assert env.route_blocked() == [(a, b)]
    new = env.call("calculate_route", destination="cuttack").data
    assert (a, b) not in list(zip(new["path"], new["path"][1:]))


def test_live_traffic_needs_the_service():
    env = CarEnvironment(make_state())
    assert env.call("get_traffic").ok
    off = CarEnvironment(make_state("traffic_offline"))
    r = off.call("get_traffic")
    assert not r.ok and "live_traffic" in r.error


def test_conflicting_calendar_has_overlapping_events():
    env = CarEnvironment(make_state("conflicting_calendar"))
    evs = env.call("get_calendar_events").data
    assert [e["start"] for e in evs[:2]] == ["15:00", "15:00"]


def test_charging_waypoint_is_used_while_driving():
    env = CarEnvironment(make_state("low_battery"))
    env.call("set_navigation", destination="cuttack", waypoints=["cs_kiit"])
    out = env.drive(15)
    assert any("charged at" in e for e in out["events"])
    assert env.vehicle["battery_pct"] >= 70


def test_waypoint_at_destination_is_not_duplicated():
    from module_1_simulator.environment import CarEnvironment
    e = CarEnvironment()
    assert e.call("set_navigation", destination="kiit_square").ok
    r = e.call("add_waypoint", waypoint="kiit_square")
    assert r.ok and r.data["already_on_route"] and e.navigation["waypoints"] == []
