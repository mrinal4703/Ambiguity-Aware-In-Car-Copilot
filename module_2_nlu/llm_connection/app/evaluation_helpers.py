"""Helpers for offline tests and evaluation: build a schema-valid fake LLM output."""


def fake_output(intent="control_climate", action="adjust_temperature", params=None,
                ambiguous=False, actions=None, utterance="Set the temperature to 22"):
    params = {"temperature": 22} if params is None else params
    if actions is None:
        actions = [{"action": action, "parameters": params, "requires_confirmation": False}]
    return {
        "intent": intent, "utterance": utterance, "rewritten_request": utterance,
        "entities": [], "constraints": {}, "action_candidates": actions, "context_references": [],
        "ambiguity": {"is_ambiguous": ambiguous, "reason": "test" if ambiguous else None,
                      "clarification_question": "Which one?" if ambiguous else None},
        "confidence": 0.9,
    }
