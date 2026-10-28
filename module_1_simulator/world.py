"""Static world data for the simulated car environment (module 1).

Everything here is SYNTHETIC: a small road network around Bhubaneswar with
illustrative coordinates, charging stations, a calendar and contacts. Values
are chosen to exercise the scenarios in the project PDF (clear requests,
ambiguity, missing capabilities, infeasible routes, unsafe requests).

Coordinates are [longitude, latitude] (GeoJSON order).
"""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

# --------------------------------------------------------------------------
# Road network
# --------------------------------------------------------------------------
LOCATIONS: dict[str, dict[str, Any]] = {
    "home":           {"name": "Home (Patia)",            "coords": [85.8180, 20.3540]},
    "kiit_square":    {"name": "KIIT Square",             "coords": [85.8300, 20.3500]},
    "infocity":       {"name": "Infocity",                "coords": [85.8050, 20.3380]},
    "chandaka":       {"name": "Chandaka",                "coords": [85.7750, 20.3550]},
    "tech_park":      {"name": "DLF Cybercity Tech Park", "coords": [85.8100, 20.3150]},
    "jaydev_vihar":   {"name": "Jaydev Vihar",            "coords": [85.8180, 20.3000]},
    "vani_vihar":     {"name": "Vani Vihar",              "coords": [85.8400, 20.2970]},
    "acharya_vihar":  {"name": "Acharya Vihar",           "coords": [85.8280, 20.2880]},
    "rasulgarh":      {"name": "Rasulgarh",               "coords": [85.8650, 20.2920]},
    "esplanade":      {"name": "Esplanade One Mall",      "coords": [85.8700, 20.3000]},
    "nh16_junction":  {"name": "NH16 Junction",           "coords": [85.8700, 20.3300]},
    "cuttack":        {"name": "Cuttack",                 "coords": [85.8800, 20.4620]},
    "master_canteen": {"name": "Master Canteen",          "coords": [85.8420, 20.2680]},
    "airport":        {"name": "Biju Patnaik Airport",    "coords": [85.8180, 20.2520]},
    "khandagiri":     {"name": "Khandagiri",              "coords": [85.7780, 20.2580]},
    "old_town":       {"name": "Old Town",                "coords": [85.8350, 20.2400]},
    "puri_junction":  {"name": "Puri Highway Junction",   "coords": [85.8600, 20.2300]},
}

# (a, b, road_type, speed_kmh, toll).  Roads are two-way.
_ROADS: list[tuple[str, str, str, float, bool]] = [
    ("home", "kiit_square", "city", 35, False),
    ("home", "infocity", "city", 40, False),
    ("home", "chandaka", "city", 45, False),
    ("infocity", "tech_park", "city", 40, False),
    ("chandaka", "khandagiri", "highway", 70, False),
    ("tech_park", "jaydev_vihar", "city", 35, False),
    ("kiit_square", "nh16_junction", "city", 40, False),
    ("kiit_square", "vani_vihar", "city", 35, False),
    ("jaydev_vihar", "acharya_vihar", "city", 30, False),
    ("jaydev_vihar", "vani_vihar", "city", 30, False),
    ("vani_vihar", "rasulgarh", "city", 35, False),
    ("rasulgarh", "esplanade", "city", 30, False),
    ("rasulgarh", "nh16_junction", "highway", 70, False),
    ("nh16_junction", "cuttack", "highway", 80, True),
    ("acharya_vihar", "master_canteen", "city", 30, False),
    ("vani_vihar", "master_canteen", "city", 30, False),
    ("master_canteen", "old_town", "city", 30, False),
    ("master_canteen", "airport", "city", 35, False),
    ("jaydev_vihar", "airport", "city", 40, False),
    ("airport", "khandagiri", "highway", 60, False),
    ("old_town", "puri_junction", "city", 35, False),
    ("rasulgarh", "puri_junction", "highway", 70, True),
]

ROAD_FACTOR = 1.25  # road distance / straight-line distance (keeps A* heuristics admissible)


def haversine_km(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def build_roads() -> list[dict[str, Any]]:
    roads = []
    for a, b, road_type, speed, toll in _ROADS:
        dist = round(haversine_km(LOCATIONS[a]["coords"], LOCATIONS[b]["coords"]) * ROAD_FACTOR, 2)
        roads.append({"from": a, "to": b, "distance_km": dist, "road_type": road_type,
                      "speed_kmh": speed, "toll": toll})
    return roads


ROADS = build_roads()

# --------------------------------------------------------------------------
# Charging stations
# --------------------------------------------------------------------------
CHARGING_STATIONS: list[dict[str, Any]] = [
    {"id": "cs_kiit", "name": "Tata Power EZ Charge, KIIT Square", "node": "kiit_square",
     "connectors": ["CCS2"], "power_kw": 50, "network": "Tata Power", "available": True, "price_per_kwh": 18},
    {"id": "cs_jaydev", "name": "Statiq Jaydev Vihar", "node": "jaydev_vihar",
     "connectors": ["CCS2", "Type2"], "power_kw": 30, "network": "Statiq", "available": True, "price_per_kwh": 16},
    {"id": "cs_techpark", "name": "ChargeZone Tech Park", "node": "tech_park",
     "connectors": ["CCS2"], "power_kw": 60, "network": "ChargeZone", "available": True, "price_per_kwh": 19},
    {"id": "cs_esplanade", "name": "Statiq Esplanade One", "node": "esplanade",
     "connectors": ["CCS2"], "power_kw": 60, "network": "Statiq", "available": True, "price_per_kwh": 17},
    {"id": "cs_airport", "name": "Airport CHAdeMO Point", "node": "airport",
     "connectors": ["CHAdeMO"], "power_kw": 50, "network": "Fortum", "available": True, "price_per_kwh": 20},
    {"id": "cs_cuttack", "name": "Tata Power Cuttack Hub", "node": "cuttack",
     "connectors": ["CCS2"], "power_kw": 120, "network": "Tata Power", "available": True, "price_per_kwh": 21},
    {"id": "cs_khandagiri", "name": "Khandagiri AC Charger", "node": "khandagiri",
     "connectors": ["Type2"], "power_kw": 7.4, "network": "Local", "available": True, "price_per_kwh": 12},
    {"id": "cs_oldtown", "name": "Old Town Fast Charger", "node": "old_town",
     "connectors": ["CCS2"], "power_kw": 50, "network": "Tata Power", "available": False, "price_per_kwh": 18},
]

# --------------------------------------------------------------------------
# Points of interest (for "tea", "somewhere to stop", ...)
# --------------------------------------------------------------------------
POIS: list[dict[str, Any]] = [
    {"id": "poi_chai_jaydev", "name": "Chai Point, Jaydev Vihar", "category": "cafe", "node": "jaydev_vihar"},
    {"id": "poi_cafe_techpark", "name": "Tea Lounge, Tech Park", "category": "cafe", "node": "tech_park"},
    {"id": "poi_ccd_kiit", "name": "Cafe Coffee Day, KIIT Square", "category": "cafe", "node": "kiit_square"},
    {"id": "poi_rest_chandaka", "name": "Chandaka Highway Rest Area", "category": "rest_area", "node": "chandaka"},
    {"id": "poi_rest_nh16", "name": "NH16 Food Plaza", "category": "rest_area", "node": "nh16_junction"},
    {"id": "poi_pharmacy_vani", "name": "Apollo Pharmacy, Vani Vihar", "category": "pharmacy", "node": "vani_vihar"},
    {"id": "poi_hospital_ac", "name": "Capital Hospital", "category": "hospital", "node": "acharya_vihar"},
]

# --------------------------------------------------------------------------
# Calendar and contacts
# --------------------------------------------------------------------------
CALENDAR: list[dict[str, Any]] = [
    {"id": "ev_review", "title": "Project review meeting", "start": "15:00", "end": "16:00",
     "location": "tech_park", "organizer": "c_priya", "attendees": ["c_priya", "c_rahul_v"]},
    {"id": "ev_dinner", "title": "Dinner with Anita", "start": "20:00", "end": "21:30",
     "location": "esplanade", "organizer": "c_anita", "attendees": ["c_anita"]},
]

CONTACTS: list[dict[str, Any]] = [
    {"id": "c_priya", "name": "Priya Sharma", "phone": "+91-90000-00001", "relation": "manager",
     "preferred_channel": "sms", "allow_messages": True},
    {"id": "c_rahul_v", "name": "Rahul Verma", "phone": "+91-90000-00002", "relation": "colleague",
     "preferred_channel": "whatsapp", "allow_messages": True},
    {"id": "c_rahul_d", "name": "Rahul Das", "phone": "+91-90000-00003", "relation": "friend",
     "preferred_channel": "sms", "allow_messages": True},
    {"id": "c_anita", "name": "Anita Gupta", "phone": "+91-90000-00004", "relation": "family",
     "preferred_channel": "sms", "allow_messages": True},
    {"id": "c_mom", "name": "Mom", "phone": "+91-90000-00005", "relation": "family",
     "preferred_channel": "call", "allow_messages": True},
    {"id": "c_landlord", "name": "Mr. Mohanty (landlord)", "phone": "+91-90000-00006", "relation": "other",
     "preferred_channel": "sms", "allow_messages": False},
]

# --------------------------------------------------------------------------
# Default mutable state
# --------------------------------------------------------------------------
DEFAULT_VEHICLE: dict[str, Any] = {
    "battery_pct": 35.0,
    "battery_capacity_kwh": 30.0,
    "consumption_kwh_per_km": 0.15,
    "connector": "CCS2",
    "speed_kmh": 40.0,
    "gear": "D",
    "location": "home",
    "ac": {"on": False, "temperature_c": 24.0, "fan": 2},
    "cabin_temperature_c": 31.0,
    "windows": {"front_left": 0, "front_right": 0, "rear_left": 0, "rear_right": 0},
    "media": {"playing": False, "source": None},
    # Features the simulated car really has. Anything else is a missing capability.
    "features": ["navigation", "climate", "windows", "messaging", "calls", "media",
                 "charging_search", "calendar", "reminders", "poi_search", "video", "live_traffic"],
}

DEFAULT_DRIVING_CONTEXT: dict[str, Any] = {
    "road_type": "city",
    "traffic": "moderate",       # light | moderate | heavy
    "weather": "clear",          # clear | rain | fog
    "outside_temperature_c": 34.0,
    "driving_difficulty": "low",  # low | medium | high
    "time": "14:10",
}

DEFAULT_NAVIGATION: dict[str, Any] = {"active": False, "destination": None, "waypoints": [], "route": None}


def default_state() -> dict[str, Any]:
    """A fresh, deep-copied initial state (reproducible)."""
    return {
        "vehicle": deepcopy(DEFAULT_VEHICLE),
        "driving": deepcopy(DEFAULT_DRIVING_CONTEXT),
        "navigation": deepcopy(DEFAULT_NAVIGATION),
        "stations": deepcopy(CHARGING_STATIONS),
        "pois": deepcopy(POIS),
        "calendar": deepcopy(CALENDAR),
        "contacts": deepcopy(CONTACTS),
        "roads": deepcopy(ROADS),
        "locations": deepcopy(LOCATIONS),
        "messages_sent": [],
        "calls": [],
        "reminders": [],
    }
