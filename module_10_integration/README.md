# Module 10: Integration and evaluation   (owner: Souymadeep)

## What this module does
Wires modules 1-9 into one copilot, runs the scenario suite with a simulated driver, computes Pass@3 / Pass^3 and
the ablation table from the PDF, and serves the agent over HTTP for the React dashboard (`frontend/`).

## Inputs and outputs
- Takes in: driver utterances (`CopilotAgent.handle(text)`), an `AgentConfig`.
- Hands on: `Turn` (reply, kind = question / confirm / done / blocked / deferred / refused / failed / answer,
  decision, candidates with probabilities, plan, tool calls, safety verdict); `RESULTS.md`; a FastAPI app.

## How to run / test
```bash
python -m pytest module_10_integration
python -m module_10_integration.run_experiments                 # all ablations, writes RESULTS.md
python -m module_10_integration.run_experiments --configs full_fixed --trials 3
uvicorn module_10_integration.api:app --port 8001               # API for the dashboard
```

## Agent loop (`agent.py`)
1. Pending clarification or confirmation? Interpret the reply (answer matching / yes-no); a stray "yes" with nothing
   pending gets "There's nothing waiting for an answer right now."
2. Parse (module 2) -> one task per sub-request; extra tasks are queued and handled after the current one.
3. Belief + internal context lookup (module 3).
4. Decide: proceed / gather context / ask (module 4 EVPI, or module 8 Q-policy with `policy="rl"`), within a
   question budget of 3.
5. Capability check (module 9); unsupported -> honest refusal with an alternative.
6. Plan + execute (module 7, which uses modules 5 and 6) with the safety gate (module 9) on every step; pause for
   confirmation; replan on failures.
7. Reply built only from verified tool results and the environment state (no claims without a successful call).

## Configurations (`config.py`)
| name | tools | uncertainty + EVPI | planning + CSP + search | safety | policy |
|---|---|---|---|---|---|
| llm_alone | no | no | no | no | top candidate |
| llm_tools | yes | no | no | no | top candidate |
| llm_uncertainty | yes | yes | no | no | EVPI |
| llm_planning | yes | no | yes | no | top candidate |
| full_fixed | yes | yes | yes | yes | EVPI |
| full_rl | yes | yes | yes | yes | Q-learning (module 8) |

## Scenarios (`scenarios.py`)
30 scenarios in 9 categories: base, indirect, ambiguous, internal_disambiguation, missing_capability, infeasible,
multi_step, changing_environment (station goes offline, tool timeout), unsafe. Each has a success check on the final
environment state, scripted answers for the simulated driver, an expected question count, and an optional
safety-violation check. Repeated execution is measured by running each scenario 3 times (trials 2-3 perturb traffic
and road speeds).

## Results (`RESULTS.md`, 30 scenarios x 3 trials)
| configuration | task success | Pass@3 | Pass^3 | questions / task | unnecessary q / task | safety violations / task | hallucinated / task |
|---|---|---|---|---|---|---|---|
| llm_alone | 0.20 | 0.20 | 0.20 | 0.00 | 0.00 | 0.00 | 1.00 |
| llm_tools | 0.60 | 0.60 | 0.60 | 0.00 | 0.00 | 0.17 | 0.07 |
| llm_uncertainty | 0.70 | 0.70 | 0.70 | 0.23 | 0.00 | 0.13 | 0.07 |
| llm_planning | 0.70 | 0.70 | 0.70 | 0.00 | 0.00 | 0.17 | 0.07 |
| full_fixed | 1.00 | 1.00 | 1.00 | 0.23 | 0.00 | 0.00 | 0.00 |
| full_rl | 1.00 | 1.00 | 1.00 | 0.30 | 0.03 | 0.00 | 0.00 |

Reading the table:
- LLM alone "succeeds" only on unsafe scenarios (doing nothing is safe) and claims success without calling a tool
  every time.
- Tools without safety cause violations (message to the landlord, AC at 35 C, windows at highway speed, a call
  during a storm, a message to an unsure recipient).
- Uncertainty fixes the ambiguous cases; planning fixes infeasible trips and changing environments; only the full
  system handles missing capabilities and all unsafe cases.
- The RL policy asks one extra question (ctx_rahul_meeting) because the PDF reward pays +2 for a useful question but
  charges for a lookup; see `module_8_rl/README.md`.

## Known limitations / TODO
- [ ] Simulated driver answers are scripted; no user study.
- [ ] Experiments use the rule-based parser for reproducibility; the LLM parser can be enabled with `parser="llm"`.

## Log (newest first)
- 2026-10-28: agent, configs, scenario suite, metrics, experiments, API, dashboard; 9 tests.
