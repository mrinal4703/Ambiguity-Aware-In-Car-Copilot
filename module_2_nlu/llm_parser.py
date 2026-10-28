"""LLM-backed NLU (module 2), optional.

Calls an OpenAI-compatible endpoint (Groq by default, same as `module_2_nlu/llm_connection/`)
with JSON mode, then validates the answer against our own schema. Any failure
falls back to the rule-based parser, so the system never depends on the LLM
being right or even reachable.

Enable by setting GROQ_API_KEY (and optionally NLU_MODEL / NLU_BASE_URL).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from pydantic import ValidationError

from .rule_parser import RuleBasedParser
from .schema import GOALS, REFERENCES, NLUResult, validate_result

SYSTEM_PROMPT = """You are the NLU layer of an in-car assistant. You NEVER execute actions.
Split the driver's utterance into tasks. For each task list up to 4 candidate goals with a
plausibility score (scores need not sum to 1). Use ONLY these goals and parameter names:
{goals}
Use these reference placeholders instead of guessing values you cannot know:
{refs}
Use null for unknown parameter values. Never invent contacts, destinations or temperatures.
Keep relative values relative ("2 degrees colder" -> delta_c = -2).
Return ONLY a JSON object of the form:
{{"tasks": [{{"text": str, "rewritten": str, "intent": str,
  "candidates": [{{"goal": str, "params": {{}}, "score": float, "rationale": str}}],
  "entities": {{}}, "constraints": {{}}, "urgency": "low|normal|high",
  "explicit_action": bool, "requires_context": bool, "missing_params": [str]}}],
 "confidence": float}}"""


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1) if m else text


class LLMParser:
    name = "llm"

    def __init__(self, complete: Callable[[str, str], str] | None = None, model: str | None = None):
        """`complete(system, user) -> str` can be injected (tests, other providers)."""
        self.fallback = RuleBasedParser()
        self.model = model or os.getenv("NLU_MODEL", "openai/gpt-oss-20b")
        self._complete = complete or self._groq_complete
        self.last_error: str | None = None

    def _groq_complete(self, system: str, user: str) -> str:
        from openai import OpenAI  # imported lazily: optional dependency
        client = OpenAI(api_key=os.environ["GROQ_API_KEY"],
                        base_url=os.getenv("NLU_BASE_URL", "https://api.groq.com/openai/v1"))
        resp = client.chat.completions.create(
            model=self.model, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return resp.choices[0].message.content or ""

    def parse(self, utterance: str, history: list[dict] | None = None,
              vehicle_context: dict | None = None) -> NLUResult:
        system = SYSTEM_PROMPT.format(goals=json.dumps(GOALS), refs=json.dumps(REFERENCES))
        user = json.dumps({"utterance": utterance, "history": (history or [])[-6:],
                           "vehicle_context": vehicle_context or {}})
        try:
            raw: Any = json.loads(_strip_fences(self._complete(system, user)))
            result = NLUResult.model_validate({"utterance": utterance, "parser": self.name, **raw})
            issues = validate_result(result)
            if issues or not any(t.candidates for t in result.tasks):
                raise ValueError("; ".join(issues) or "no candidates")
            return result
        except (ValueError, ValidationError, KeyError, json.JSONDecodeError, Exception) as e:  # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"
            out = self.fallback.parse(utterance, history, vehicle_context)
            out.notes.append(f"LLM output rejected, used rules ({self.last_error[:120]})")
            return out


def make_parser(prefer_llm: bool | None = None):
    """LLM parser if a key is configured (or explicitly requested), else rules."""
    use_llm = bool(os.getenv("GROQ_API_KEY")) if prefer_llm is None else prefer_llm
    return LLMParser() if use_llm else RuleBasedParser()
