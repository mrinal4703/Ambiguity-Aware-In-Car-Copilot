from app.schemas import IntentOutput
from app.taxonomy import INTENT_TAXONOMY


class NLUValidator:

    @staticmethod
    def validate(data: dict) -> IntentOutput:

        # Validate the Pydantic schema.
        result = IntentOutput.model_validate(data)

        # Validate intent.
        if result.intent not in INTENT_TAXONOMY:
            raise ValueError(
                f"Unsupported intent: {result.intent}"
            )

        # Validate action-intent consistency.
        allowed_actions = INTENT_TAXONOMY[result.intent]

        for candidate in result.action_candidates:

            if candidate.action not in allowed_actions:
                raise ValueError(
                    f"Action {candidate.action} "
                    f"is invalid for intent {result.intent}"
                )

        # Validate ambiguity consistency.
        if result.ambiguity.is_ambiguous:
            if not result.ambiguity.reason:
                raise ValueError(
                    "Ambiguous output must contain a reason"
                )

        return result

    @staticmethod
    def safe_action_candidates(
        result: IntentOutput
    ) -> list[dict]:

       
        allowed = INTENT_TAXONOMY[result.intent]

        return [
            candidate.model_dump()
            for candidate in result.action_candidates
            if candidate.action in allowed
        ]