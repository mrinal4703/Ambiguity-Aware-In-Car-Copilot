from app.intent_parser import IntentParser


class CopilotOrchestrator:
    def __init__(self):
        self.nlu = IntentParser()

    def process(self, utterance, history, vehicle_context):

        # Get NLU output
        nlu_response = self.nlu.parse(
            utterance=utterance,
            history=history,
            vehicle_context=vehicle_context
        )

        # Extract structured intent
        intent_result = nlu_response["intent_result"]

        # Pass to other modules
        return {
            "intent": intent_result,
            "reflection": nlu_response["reflection"]
        }