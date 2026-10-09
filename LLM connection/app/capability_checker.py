
class CapabilityChecker:

    def check_action_support(
        self,
        action_candidates: list[dict],
        capabilities: list[str]
    ):
        supported = []
        unsupported = []

        for candidate in action_candidates:
            action = candidate.get("action")

            if action in capabilities:
                supported.append(candidate)
            else:
                unsupported.append(candidate)

        return {
            "supported_actions": supported,
            "unsupported_actions": unsupported
        }
