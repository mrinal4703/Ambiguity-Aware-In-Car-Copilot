"""Evaluate the NLU service against a labelled dataset (fix B6).

Usage (server running on port 8000, from inside module_2_nlu/llm_connection):
    python evaluation/evaluate.py [path/to/dataset.json]

Defaults to data/test_dataset.json and falls back to data/nlu_dataset.json.
Uses httpx (already in requirements.txt) instead of requests.
"""
import json
import sys
from pathlib import Path

import httpx

API_URL = "http://127.0.0.1:8000/nlu/parse"
ROOT = Path(__file__).resolve().parents[1]


def load_dataset(path: str | None = None) -> list[dict]:
    candidates = [Path(path)] if path else [ROOT / "data/test_dataset.json", ROOT / "data/nlu_dataset.json"]
    for p in candidates:
        if p.exists() and p.read_text().strip():
            data = json.loads(p.read_text())
            if data:
                return data
    raise SystemExit("No non-empty dataset found")


def unwrap(output: dict) -> dict:
    """The API returns {intent_result, reflection}; older versions returned the intent directly."""
    return output.get("intent_result", output)


def score(dataset: list[dict], outputs: list[dict | None]) -> dict:
    total = len(dataset)
    valid = intent_ok = action_ok = amb_ok = 0
    for sample, output in zip(dataset, outputs):
        if output is None:
            continue
        valid += 1
        out = unwrap(output)
        intent_ok += out.get("intent") == sample["expected_intent"]
        actions = [a["action"] for a in out.get("action_candidates", [])]
        exp = sample["expected_action"]
        action_ok += (not actions) if exp is None else (exp in actions)
        amb_ok += out.get("ambiguity", {}).get("is_ambiguous", False) == sample["expected_ambiguity"]
    return {"n": total, "intent_accuracy": intent_ok / total, "action_accuracy": action_ok / total,
            "ambiguity_accuracy": amb_ok / total, "valid_output_rate": valid / total}


def main() -> None:
    dataset = load_dataset(sys.argv[1] if len(sys.argv) > 1 else None)
    outputs: list[dict | None] = []
    with httpx.Client(timeout=60) as client:
        for i, sample in enumerate(dataset):
            try:
                r = client.post(API_URL, json={"session_id": f"evaluation_{i}", "utterance": sample["utterance"],
                                               "vehicle_context": sample.get("vehicle_context", {})})
                r.raise_for_status()
                outputs.append(r.json())
            except httpx.HTTPError as e:
                print(f"Request failed for sample {i}: {e}")
                outputs.append(None)
    for k, v in score(dataset, outputs).items():
        print(f"{k}: {v:.3f}" if isinstance(v, float) else f"{k}: {v}")


if __name__ == "__main__":
    main()
