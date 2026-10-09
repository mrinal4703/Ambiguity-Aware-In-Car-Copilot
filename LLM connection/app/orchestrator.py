from app.intent_parser import IntentParser
from app.charging_router import ChargingRouter


class CopilotOrchestrator:
    def __init__(self):
        self.nlu = IntentParser()
        self.charging_router = ChargingRouter()

    def process(self, utterance, history, vehicle_context):
        # 1. Run the existing NLU pipeline
        nlu_response = self.nlu.parse(
            utterance=utterance,
            history=history,
            vehicle_context=vehicle_context,
        )

        intent_result = nlu_response["intent_result"]
        reflection = nlu_response["reflection"]

        # 2. Check reflection
        if (
            isinstance(reflection, dict)
            and reflection.get("is_valid") is False
        ):
            return {
                "status": "invalid",
                "intent": intent_result,
                "reflection": reflection,
            }

        # 3. Check ambiguity
        ambiguity = intent_result.get("ambiguity", {})

        if ambiguity.get("is_ambiguous", False):
            return {
                "status": "clarification_required",
                "question": (
                    ambiguity.get("clarification_question")
                    or "Could you clarify your request?"
                ),
                "intent": intent_result,
            }

        # 4. Detect a charging request (prototype)
        text = utterance.lower()

        charging_phrases = (
            "out of charge",
            "low on charge",
            "running low on charge",
            "low battery",
            "battery is low",
            "need to charge",
            "charging station",
            "running low on battery",
        )

        is_charging_request = any(
            phrase in text for phrase in charging_phrases
        )

        if not is_charging_request:
            return {
                "status": "ready",
                "intent": intent_result,
                "reflection": reflection,
            }

        # 5. Check required vehicle state
        battery = vehicle_context.get("battery_percent")
        remaining_range = vehicle_context.get(
            "estimated_range_km"
        )

        if battery is None or remaining_range is None:
            return {
                "status": "missing_vehicle_state",
                "message": (
                    "Please provide the current battery percentage "
                    "and estimated remaining range."
                ),
                "intent": intent_result,
            }

        try:
            battery = float(battery)
            remaining_range = float(remaining_range)
        except (TypeError, ValueError):
            return {
                "status": "invalid_vehicle_state",
                "message": (
                    "Battery percentage and estimated range "
                    "must be numeric values."
                ),
                "intent": intent_result,
            }

        if not 0 <= battery <= 100 or remaining_range <= 0:
            return {
                "status": "vehicle_cannot_proceed",
                "message": (
                    "Provide a battery percentage from 0 to 100 "
                    "and a positive estimated range."
                ),
                "intent": intent_result,
            }

        # 6. Resolve the current location and destination
        current_location = vehicle_context.get(
            "current_location"
        )
        destination = vehicle_context.get("destination")

        if not current_location or not destination:
            return {
                "status": "missing_trip_details",
                "message": (
                    "Please provide the current location and "
                    "destination before calculating the route."
                ),
                "intent": intent_result,
            }

        # 7. Calculate a route through the demo charging station
        trip = {
            **vehicle_context,
            "current_location": current_location,
            "destination": destination,
            "battery_percent": battery,
            "estimated_range_km": remaining_range,
        }

        route_result = self.charging_router.find_charging_route(
            trip
        )

        if not route_result.get("feasible", False):
            return {
                "status": "no_feasible_route",
                "message": route_result.get(
                    "reason",
                    "No feasible charging route was found.",
                ),
                "intent": intent_result,
            }

        # 8. Return route data for the frontend map
        return {
            "status": "route_updated",
            "message": (
                "A demo route via the charging station "
                "has been calculated."
            ),
            "intent": intent_result,
            "reflection": reflection,
            "route": {
                **route_result,
                "origin": current_location,
                "destination": destination,
            },
        }