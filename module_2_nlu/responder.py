"""Natural-language responses (module 2, GenAI side).

The copilot's replies are first built as *templates* from verified tool results
(module 10). An LLM may then rephrase a reply so it sounds natural and stays short
for a driver, but it may not change the facts. `GroundedResponder` checks every
rewrite and falls back to the template if the LLM

  * drops or changes a number (distance, minutes, %, time, temperature),
  * drops or invents a proper name (station, place, contact),
  * turns a question into a statement or the other way round,
  * claims something was done ("I've sent", "done") that the template did not claim,
  * gets longer than the template plus a small margin (drivers need concise answers).

Without GROQ_API_KEY (tests, experiments) the template is returned unchanged.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

SYSTEM = """You rephrase replies of an in-car assistant for a driver who is driving.
Keep every number, time, name and place exactly as given. Do not add facts, offers or actions.
Keep questions as questions. Be brief: at most the length of the original. Reply with the text only."""

_NUM = re.compile(r"\d+(?:[.:]\d+)?")
_DONE = re.compile(r"\b(i(?:'ve| have)? (sent|called|set|started|added|opened|turned)|done|completed)\b", re.I)
_STOP = {"I", "The", "A", "An", "Sorry", "Okay", "Ok", "Yes", "No", "Do", "Should", "Would", "Shall", "Can",
         "What", "Which", "Who", "Where", "When", "How", "It", "That", "This", "There", "You", "Your", "Is",
         "Start", "Add", "Send", "Call", "Navigating", "Opening", "Charge", "Best", "Closest", "Sent"}


def _names(text: str) -> set[str]:
    """Capitalised words that are not just the first word of a sentence."""
    out = set()
    for sentence in re.split(r"(?<=[.?!:])\s+", text):
        words = re.findall(r"[A-Za-z][\w'-]*", sentence)
        out.update(w for w in words[1:] if w[0].isupper() and w not in _STOP)
    return out


def grounding_issues(template: str, rewrite: str, max_growth: float = 1.15) -> list[str]:
    issues = []
    if sorted(_NUM.findall(template)) != sorted(_NUM.findall(rewrite)):
        issues.append("numbers changed")
    missing = _names(template) - _names(rewrite)
    added = _names(rewrite) - _names(template)
    if missing:
        issues.append(f"names dropped: {sorted(missing)}")
    if added:
        issues.append(f"names added: {sorted(added)}")
    if template.rstrip().endswith("?") != rewrite.rstrip().endswith("?"):
        issues.append("question/statement changed")
    if _DONE.search(rewrite) and not _DONE.search(template):
        issues.append("claims an action that was not verified")
    if len(rewrite) > len(template) * max_growth + 10:
        issues.append("longer than the template")
    if not rewrite.strip():
        issues.append("empty")
    return issues


@dataclass
class GroundedResponder:
    complete: Callable[[str, str], str] | None = None
    model: str | None = None
    rejected: list[tuple[str, str, list[str]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.complete is None and os.getenv("GROQ_API_KEY"):
            self.complete = self._groq
        self.model = self.model or os.getenv("NLU_MODEL", "openai/gpt-oss-20b")

    @property
    def enabled(self) -> bool:
        return self.complete is not None

    def _groq(self, system: str, user: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["GROQ_API_KEY"],
                        base_url=os.getenv("NLU_BASE_URL", "https://api.groq.com/openai/v1"))
        r = client.chat.completions.create(model=self.model, temperature=0.2,
                                           messages=[{"role": "system", "content": system},
                                                     {"role": "user", "content": user}])
        return (r.choices[0].message.content or "").strip()

    def phrase(self, template: str) -> str:
        """Return an LLM rewrite of `template` if it passes the grounding check, else the template."""
        if not self.enabled or not template:
            return template
        try:
            out = self.complete(SYSTEM, template).strip().strip('"')
        except Exception as e:  # noqa: BLE001 - never let phrasing break the copilot
            self.rejected.append((template, "", [f"error: {e}"]))
            return template
        issues = grounding_issues(template, out)
        if issues:
            self.rejected.append((template, out, issues))
            return template
        return out
