# Module 4: EVPI clarification   (owner: Mrinal, tentative)

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
```

## Assumptions and limitations
- Probabilities in the demo are hypothetical (from the PDF's tea example), not measured.
- EVPI here is a probability-gain proxy, not utility-based EVPI. Check against Suri et al. (2026).
- Answers are assumed truthful and drawn from the candidate values; an unmatched answer returns `matched=False`
  and the orchestrator should re-parse with NLU.
- Questions are template-worded; pass a `phraser` callable to let an LLM reword them.
- Safety is not considered here: module 9 still validates whatever is proceeded with.

## TODO
- [ ] Agree the `BeliefState` fields with Swastika (module 3)
- [ ] Agree the feature list with Jana (module 8)
- [ ] Hook into the orchestrator's ambiguity step (coordinate with Arjo)
- [ ] LLM phraser for natural question wording
- [ ] Noisy-answer model (user may answer unreliably)
- [ ] Utility-based EVPI variant and comparison
- [ ] Evaluation vs always-ask and fixed-threshold baselines on a scenario set

## Log (newest first)
- 2026-10-20: starter implementation, 18 tests, demo.
