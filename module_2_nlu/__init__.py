"""Module 2: NLU and LLM layer (owner: Arjo).

`RuleBasedParser` (offline, deterministic) and `LLMParser` (Groq / OpenAI-compatible,
validated, falls back to rules) both return an `NLUResult` with weighted goal
candidates per task. The original FastAPI NLU service lives in `LLM connection/`.
"""
from .llm_parser import LLMParser, make_parser
from .rule_parser import RuleBasedParser, classify_confirmation, find_location, parse_task, split_tasks
from .schema import GOALS, REFERENCES, GoalCandidate, NLUResult, Task, validate_result

__all__ = ["LLMParser", "make_parser", "RuleBasedParser", "classify_confirmation", "find_location",
           "parse_task", "split_tasks", "GOALS", "REFERENCES", "GoalCandidate", "NLUResult", "Task",
           "validate_result"]
