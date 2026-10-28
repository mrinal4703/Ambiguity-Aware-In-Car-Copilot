# Module 4: EVPI clarification   (owner: Mrinal)

## What this module does
Given a `BeliefState` (candidate tool calls with probabilities from module 3), decide whether to
**proceed**, **gather context internally**, or **ask the user** the single most valuable question.

## Inputs and outputs
- Takes in: `BeliefState`, `ClarificationHistory`, optional set of parameters the system can look up itself.
- Hands on: `ClarificationDecision` (kind, question, options, parameter, scores).
- Also exposes `belief_features(...)`: numeric uncertainty summary for the RL state (module 8).

## How it decides (`EVPIClarifier.decide`)
1. Top candidate probability >= `execute_threshold` (0.80) -> PROCEED.
2. Candidates disagree on nothing -> PROCEED.
3. A disagreeing parameter can be looked up internally -> GATHER_CONTEXT (no question budget used).
4. Question budget used up -> PROCEED with the top candidate.
5. Otherwise score each disagreeing parameter: `Score = EVPI - lambda * Redundancy`
   - `EVPI` = expected best-candidate probability after the answer minus the best probability now
   - `Redundancy` = how often this parameter was already asked
   If the best score < `min_score` -> PROCEED, else ASK it.

The candidate's tool name is treated as the pseudo-parameter `tool`, so "what do you want to do" questions
use the same machinery as "which contact" questions.

## Run
```bash
python -m pytest module_4_evpi
python -m module_4_evpi.demo
python -m module_4_evpi.evaluate     # EVPI vs baselines on simulated dialogues
```

## Extensions
- `utility_evpi.py`: utility-based EVPI, E[max_a U(a, answer)] - max_a E[U(a)], with a cost for wrong actions, so a
  question is only worth asking if the answer can change the chosen action.
- `answer_matching.py`: matches free-text answers to candidate values (exact, alias, 5-letter stem prefix, "the
  first one"); unmatched answers return `matched=False` and go back to NLU.
- `baselines.py`: always-execute, always-clarify, fixed-threshold.

## Results (`python -m module_4_evpi.evaluate`)
| policy | success | questions / dialogue | useful | unneeded | internal lookups |
|---|---|---|---|---|---|
| always_execute | 0.661 | 0.000 | 0.000 | 0.000 | 0.000 |
| always_clarify | 1.000 | 1.101 | 0.938 | 0.189 | 0.000 |
| fixed_threshold | 0.979 | 0.910 | 0.835 | 0.000 | 0.000 |
| evpi | 0.983 | 0.729 | 0.729 | 0.000 | 0.135 |

EVPI keeps almost all of always-clarify's success while asking about a third fewer questions, none of them
unnecessary, because it looks up resolvable parameters itself first.

## Risk-aware clarification (problem-statement review)
`decide(..., risk="auto", question_cost=c)`: the execute threshold depends on how costly a wrong action is
(low 0.65 / medium 0.80 / high 0.90, from `RISK_OF_TOOL`: messages, calls and windows are high risk), and a question
is asked only if its utility-based EVPI exceeds the distraction cost `c`, which module 10 sets from the driving load.
Without `risk` the behaviour is unchanged (the reported results above).

## Assumptions and limitations
- Probabilities in the demo are hypothetical (from the PDF's tea example), not measured.
- EVPI here is a probability-gain proxy, not utility-based EVPI. Check against Suri et al. (2026).
- Answers are assumed truthful and drawn from the candidate values; an unmatched answer returns `matched=False`
  and the orchestrator should re-parse with NLU.
- Questions are template-worded; pass a `phraser` callable to let an LLM reword them.
- Safety is not considered here: module 9 still validates whatever is proceeded with.

## TODO
- [x] Agree the `BeliefState` fields with module 3
- [x] Agree the feature list with module 8 (`belief_features`)
- [x] Hook into the orchestrator (module 10)
- [x] Utility-based EVPI variant
- [x] Evaluation vs always-ask and fixed-threshold baselines
- [ ] LLM phraser for natural question wording
- [ ] Noisy-answer model (user may answer unreliably)

## Log (newest first)
- 2026-10-28 (problem-statement review): risk-aware thresholds and question cost; 35 tests.
- 2026-10-28: utility EVPI, answer matching, baselines, evaluation; 32 tests.
- 2026-10-20: starter implementation, 18 tests, demo.
