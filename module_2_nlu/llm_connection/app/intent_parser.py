
import json
import logging

from app.llm_client import LLMClient
from app.prompts import build_user_prompt
from app.validator import NLUValidator
from app.rewrite_engine import RewriteEngine
from app.ambiguity_detector import AmbiguityDetector
from app.reference_resolver import ReferenceResolver
from app.reflect_checker import ReflectChecker
from app.capability_checker import CapabilityChecker
from app.taxonomy import ALLOWED_ACTIONS

logger = logging.getLogger(__name__)


class IntentParser:

    def __init__(self, llm: LLMClient | None = None):
        # The LLM client can be injected (tests use a fake one).
        self.llm = llm or LLMClient()
        self.validator = NLUValidator()

        self.rewrite_engine = RewriteEngine()
        self.ambiguity_detector = AmbiguityDetector()
        self.reference_resolver = ReferenceResolver()
        self.reflect_checker = ReflectChecker()
        self.capability_checker = CapabilityChecker()

    def parse(
        self,
        utterance: str,
        history: list[dict],
        vehicle_context: dict
    ):
        prompt = build_user_prompt(
            utterance=utterance,
            history=history,
            vehicle_context=vehicle_context
        )

        raw_output = self.llm.generate(prompt)

        logger.debug("Raw LLM output: %s", raw_output)

        # Convert JSON string into a Python dictionary.
        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"LLM returned invalid JSON: {e}"
                )

        if not isinstance(raw_output, dict):
            raise ValueError(
                "LLM output must be a JSON object"
            )

        logger.debug(
            "Intent %s, actions %s",
            raw_output.get("intent"),
            raw_output.get("action_candidates"),
        )

        # Stage 1: Rewrite
        raw_output = self.rewrite_engine.rewrite(raw_output)

        # Stage 2: Resolve context-dependent values
        raw_output = self.reference_resolver.resolve(
            result=raw_output,
            history=history,
            vehicle_context=vehicle_context
        )

        # Stage 3: Ambiguity assessment
        raw_output = self.ambiguity_detector.assess(raw_output)

        # Stage 4: Validate the structured output
        validated_output = self.validator.validate(raw_output)

        # Convert Pydantic output to dictionary
        result = validated_output.model_dump()

        # Stage 4b: Capability check (fix B7). The vehicle context may list the
        # car's capabilities; otherwise every taxonomy action is assumed present.
        capabilities = vehicle_context.get("capabilities") or sorted(ALLOWED_ACTIONS)
        result["capability_check"] = self.capability_checker.check_action_support(
            result.get("action_candidates", []), capabilities
        )

        # Stage 5: Reflect and check consistency
        reflection = self.reflect_checker.check(result)
        result["reflection"] = reflection

        return {
            "intent_result": result,
            "reflection": reflection
        }
