class RewriteEngine:
    def rewrite(self, result: dict) -> dict:
        rewritten = result.get("rewritten_request", "").strip()

        if not rewritten:
            result["rewritten_request"] = (
                result.get("original_utterance", "")
            )

        return result