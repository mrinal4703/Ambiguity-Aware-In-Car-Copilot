INTENT_TAXONOMY = {
    "control_climate": [
        "adjust_temperature",
        "turn_on_ac",
        "turn_off_ac",
        "adjust_fan_speed"
    ],
    "navigate": [
        "start_navigation",
        "cancel_navigation",
        "change_destination"
    ],
    "control_media": [
        "play_music",
        "pause_music",
        "skip_track",
        "change_media"
    ],
    "adjust_volume": [
        "increase_volume",
        "decrease_volume",
        "mute_audio"
    ],
    "make_call": [
        "call_contact",
        "answer_call",
        "end_call"
    ],
    "search_poi": [
        "search_nearby_places"
    ],
    "weather_query": [
        "get_weather"
    ],
    "vehicle_information": [
        "get_vehicle_information"
    ],
    "calendar_query": [
        "get_calendar_events"
    ],
    "unknown": []
}

ALLOWED_ACTIONS = {
    action
    for actions in INTENT_TAXONOMY.values()
    for action in actions
}