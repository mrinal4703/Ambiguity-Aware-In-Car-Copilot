import json
from typing import Any


class ReferenceResolver:

    def _parse_content(self, content: Any) -> dict:
        """Convert stored history content into a dictionary."""
        if isinstance(content, dict):
            return content

        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return {}

    def _get_previous_actions(self, history: list[dict]) -> list[dict]:
        """Extract action candidates from previous assistant responses."""
        previous_actions = []

        for message in reversed(history):
            if message.get("role") != "assistant":
                continue

            content = self._parse_content(message.get("content"))

            actions = content.get("action_candidates", [])

            if isinstance(actions, list):
                previous_actions.extend(reversed(actions))

        return previous_actions

    def resolve(
        self,
        result: dict,
        history: list[dict],
        vehicle_context: dict | None = None
    ) -> dict:

        vehicle_context = vehicle_context or {}

        references = result.get("context_references", [])

        # No contextual references: nothing to resolve.
        if not references:
            return result

        previous_actions = self._get_previous_actions(history)

        for action in result.get("action_candidates", []):
            parameters = action.setdefault("parameters", {})

            for key, value in parameters.items():

                # Resolve only missing or explicitly unresolved values.
                if value not in (None, "", "unknown", "unresolved"):
                    continue

                # First, look for the same parameter in previous actions.
                for previous in previous_actions:
                    previous_parameters = previous.get("parameters", {})

                    if key in previous_parameters:
                        previous_value = previous_parameters[key]

                        if previous_value not in (
                            None, "", "unknown", "unresolved"
                        ):
                            parameters[key] = previous_value
                            break

                # If history did not resolve it, check matching vehicle context.
                if parameters.get(key) in (
                    None, "", "unknown", "unresolved"
                ):
                    if key in vehicle_context:
                        parameters[key] = vehicle_context[key]

        return result