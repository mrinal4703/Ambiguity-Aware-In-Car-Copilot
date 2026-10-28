"""Match a driver's free-text reply to one of the offered options (module 4).

Order of strategies: ordinal ("the first one") -> exact value/label -> substring
-> token overlap. Returns the matched option *value* or None (then the
orchestrator re-parses the reply with the NLU, because the meaning may be
outside the candidate set).
"""
from __future__ import annotations

import re
from typing import Any, Sequence

ORDINALS = {"first": 0, "1st": 0, "one": 0, "second": 1, "2nd": 1, "two": 1, "third": 2, "3rd": 2, "three": 2,
            "last": -1}
STOP = {"the", "a", "an", "to", "please", "i", "want", "would", "like", "mean", "one", "do", "my", "me", "it",
        "go", "with", "just", "for", "find", "of", "and", "or", "yes"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower().replace("_", " ")) if t not in STOP}


def match_answer(reply: str, options: Sequence[Any], labels: Sequence[str] | None = None) -> Any | None:
    if not options:
        return None
    labels = list(labels) if labels is not None else [str(o) for o in options]
    text = reply.lower().strip(" .!?")
    m = re.search(r"\b(first|1st|second|2nd|third|3rd|last)\b", text) or \
        re.fullmatch(r"(?:option |number )?(one|two|three|[123])", text)
    if m:
        word = m.group(1)
        idx = int(word) - 1 if word.isdigit() else ORDINALS[word]
        if -len(options) <= idx < len(options):
            return options[idx]
    for o, lab in zip(options, labels):
        if text in {str(o).lower(), lab.lower(), str(o).lower().replace("_", " ")}:
            return o
    hits = [o for o, lab in zip(options, labels)
            if any(len(t) > 2 and (t in text or (len(t) > 5 and t[:5] in text))
                   for t in _tokens(lab) | _tokens(str(o)))]
    if len(hits) == 1:
        return hits[0]
    rt = _tokens(text)
    scored = sorted(((len(rt & (_tokens(lab) | _tokens(str(o)))), i) for i, (o, lab) in
                     enumerate(zip(options, labels))), reverse=True)
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return options[scored[0][1]]
    return None
