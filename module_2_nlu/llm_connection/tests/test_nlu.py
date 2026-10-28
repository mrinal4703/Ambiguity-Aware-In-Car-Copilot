"""Offline tests for the NLU service: the LLM is replaced by a fake client."""
import json

import pytest

from app.ambiguity_detector import AmbiguityDetector
from app.evaluation_helpers import fake_output  # noqa: F401  (documented helper)
from app.intent_parser import IntentParser
from app.orchestrator import CopilotOrchestrator, is_charging_request
from app.reference_resolver import ReferenceResolver
from app.rewrite_engine import RewriteEngine


class FakeLLM:
    def __init__(self, output):
        self.output = output

    def generate(self, prompt):
        return json.loads(json.dumps(self.output))


def out(**kw):
    return fake_output(**kw)


def test_parse_valid_output_and_capability_check():
    p = IntentParser(llm=FakeLLM(out()))
    r = p.parse("Set the temperature to 22", [], {})
    assert r["intent_result"]["intent"] == "control_climate"
    assert r["reflection"]["passed"] is True
    assert r["intent_result"]["capability_check"]["unsupported_actions"] == []


def test_invalid_action_for_intent_raises():
    bad = out(action="play_music")
    with pytest.raises(ValueError):
        IntentParser(llm=FakeLLM(bad)).parse("x", [], {})


def test_rewrite_fallback_uses_utterance():  # B3
    r = RewriteEngine().rewrite({"utterance": "hello", "rewritten_request": ""})
    assert r["rewritten_request"] == "hello"


def test_ambiguity_flag_without_reason_is_kept():  # B13
    r = AmbiguityDetector().assess({"intent": "navigate", "ambiguity": {"is_ambiguous": True}})
    assert r["ambiguity"]["is_ambiguous"] is True


def test_resolver_reads_nested_history_and_does_not_fill_temperature():  # B2, B4
    history = [{"role": "assistant", "content": json.dumps(
        {"intent_result": {"action_candidates": [{"action": "start_navigation",
                                                  "parameters": {"destination": "airport"}}]}})}]
    result = {"context_references": ["there"], "action_candidates": [
        {"action": "change_destination", "parameters": {"destination": None}},
        {"action": "adjust_temperature", "parameters": {"temperature": None}}]}
    r = ReferenceResolver().resolve(result, history, {"temperature": 24})
    assert r["action_candidates"][0]["parameters"]["destination"] == "airport"
    assert r["action_candidates"][1]["parameters"]["temperature"] is None


def test_reflection_failure_is_reported():  # B1
    o = out(actions=[], ambiguous=False)
    orch = CopilotOrchestrator(nlu=IntentParser(llm=FakeLLM(o)))
    r = orch.process("set it", [], {})
    assert r["status"] == "invalid"


def test_charging_detected_before_ambiguity():  # B5
    o = out(intent="manage_charging", action="find_charging_station", ambiguous=True, params={})
    orch = CopilotOrchestrator(nlu=IntentParser(llm=FakeLLM(o)))
    ctx = {"battery_percent": 30, "estimated_range_km": 12, "current_location": "Origin",
           "destination": "Destination"}
    r = orch.process("I'm running low on battery", [], ctx)
    assert r["status"] == "route_updated"
    assert r["route"]["path"][0] == "Origin"
    assert is_charging_request("need to charge", {})
