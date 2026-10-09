class ReflectChecker:
    def check(self, result: dict) -> dict:
        issues = []

        if not result.get("intent"):
            issues.append("Missing intent")

        if not result.get("rewritten_request"):
            issues.append("Missing rewritten request")

        ambiguity = result.get("ambiguity", {})

        if ambiguity.get("is_ambiguous"):
            if not ambiguity.get("clarification_question"):
                issues.append(
                    "Ambiguous request has no clarification question"
                )

        if (
            not result.get("action_candidates")
            and not ambiguity.get("is_ambiguous")
        ):
            issues.append(
                "No action candidate for a clear request"
            )

        return {
            "passed": len(issues) == 0,
            "issues": issues
        }