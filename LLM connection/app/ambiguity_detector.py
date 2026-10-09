class AmbiguityDetector:
    def assess(self, result: dict) -> dict:
        ambiguity = result.get("ambiguity", {})

        reasons = []

        if result.get("intent") == "unknown":
            reasons.append("Intent could not be identified")

        if ambiguity.get("reason"):
            reasons.append(ambiguity["reason"])

        ambiguity["is_ambiguous"] = bool(reasons)
        ambiguity["reason"] = (
            "; ".join(reasons) if reasons else None
        )

        result["ambiguity"] = ambiguity

        return result