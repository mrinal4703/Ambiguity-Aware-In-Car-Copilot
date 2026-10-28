# Module 2: NLU and LLM   (owner: Arjo)

## What this module does
Turns a driver utterance into one or more tasks, each with several candidate goals and plausibility scores. It
never executes anything. Two interchangeable parsers share one schema: a deterministic rule-based parser (default,
used in tests and experiments) and an LLM parser (Groq / OpenAI-compatible JSON mode) that is validated against the
schema and falls back to the rules on any error. `LLM connection/` holds the earlier FastAPI NLU backend with its
bugs fixed.

## Inputs and outputs
- Takes in: utterance text (+ optional dialogue history).
- Hands on: `NLUResult` -> list of `Task` (text, rewritten, intent, `GoalCandidate`s, constraints, urgency,
  explicit_action, requires_context, missing_params). Consumed by module 3.

## How to run / test
```bash
python -m pytest module_2_nlu "LLM connection/tests"
python -c "from module_2_nlu import RuleBasedParser as P; print(P().parse('I need tea and message Priya I will be late'))"
# optional LLM parser: export GROQ_API_KEY=...  (NLU_MODEL, NLU_BASE_URL optional)
```

## Design notes
- Multi-task splitting on "and", "then" and commas; first-person rewriting for messages.
- Relative values stay relative ("make it cooler" -> delta_c -2); "at 6" -> 18:00; "avoiding tolls" -> constraint.
- References the parser cannot know (my next meeting, my manager, "him") are emitted as placeholders and resolved
  by module 3 with tools, never guessed.
- `LLM connection/`: fixed the reflection key mismatch, history resolution and the evaluation script; added
  evaluation helpers and tests.

## Problem-statement additions
- Example requests from the PDF: "I'm tired" -> rest stop / cafe / chat; "I'm running late" -> message the meeting /
  fastest route / ETA; "turn on parking assist" and "keep me in my lane" -> unsupported-feature refusals.
- New goals: `info_traffic`, `info_eta`, `chat`; reference `@current_destination`; "actually take me to X instead"
  is a destination change.
- Tolls: "avoiding tolls" is a soft preference, "no tolls at all" a hard constraint (`avoid_tolls_strict`).
  "A charger near my next appointment" sets a hard `charge_near` constraint.
- `responder.py` (`GroundedResponder`): optional LLM rewording of the reply; it is rejected and the template is used if
  the LLM adds numbers, names or claims that are not in the verified tool results.

## Known limitations / TODO
- [ ] Rule coverage is limited to the vocabulary in the scenario suite.
- [ ] LLM parser is not used in the reported experiments (no key in CI), to keep them reproducible.

## Log (newest first)
- 2026-10-28 (problem-statement review): PDF example requests, new goals, soft vs strict tolls, grounded responder; 35 + 7 tests.
- 2026-10-28: rule parser + LLM parser with schema validation and fallback; LLM connection fixes; 27 + 7 tests.
