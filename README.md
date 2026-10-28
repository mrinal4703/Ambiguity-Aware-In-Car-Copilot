# Ambiguity-Aware In-Car Copilot

A hybrid AI agent for an in-car assistant. Requests are interpreted into several candidate meanings, uncertainty
is estimated and reduced with internal lookups or a single well-chosen question (EVPI), routes and charging plans
are computed with search and constraint satisfaction, a planner executes tool calls step by step with replanning,
a deterministic safety layer can block or defer any action, and only tool-verified outcomes are reported.
Everything runs against a simulated car around Bhubaneswar.

## Architecture
```
driver utterance
  -> module 2  NLU (rules or LLM)            -> tasks with candidate goals
  -> module 3  uncertainty + context lookup   -> belief (probabilities)
  -> module 4  EVPI  /  module 8 RL policy    -> proceed | look up | ask | confirm
  -> module 9  capability check               -> refuse with alternative if unsupported
  -> module 7  plan + execute                 -> uses module 5 (A* routes) and module 6 (charging CSP)
       every step: module 9 safety gate (allow / confirm / defer / block) + result verification
  -> module 1  simulated car (tools, state, dynamic events)
  -> module 10 reply built from verified state; scenarios, metrics, API, dashboard
```

## Modules
| # | Module | Owner | Folder |
|---|---|---|---|
| 1 | Simulator and environment | Ramesh | `module_1_simulator/` |
| 2 | NLU and LLM | Arjo | `module_2_nlu/`, `LLM connection/` |
| 3 | Uncertainty estimation | Swastika | `module_3_uncertainty/` |
| 4 | EVPI clarification | Mrinal | `module_4_evpi/` |
| 5 | Search and route optimisation | Sistu Neha | `module_5_search/` |
| 6 | CSP and feasibility | Prasanna | `module_6_csp/` |
| 7 | Sequential planning | Dipanjana | `module_7_planning/` |
| 8 | Reinforcement learning | Jana | `module_8_rl/` |
| 9 | Safety and policy | Nishkarsh | `module_9_safety/` |
| 10 | Integration, evaluation, API, dashboard | Souymadeep | `module_10_integration/`, `frontend/` |

Details, inputs/outputs and status: [docs/MODULES.md](docs/MODULES.md). Each module folder has its own README.
Shared data shapes are in `contracts/`.

## Run
```bash
pip install -r requirements-dev.txt
python -m pytest                                        # all modules (about 170 tests, a few seconds)

python -m module_10_integration.run_experiments         # scenario suite + ablation -> module_10_integration/RESULTS.md
python -m module_8_rl.evaluate                          # RL vs baselines -> module_8_rl/RESULTS.md
python -m module_4_evpi.evaluate                        # EVPI vs baselines
python -m module_5_search.compare                       # A* vs UCS

uvicorn module_10_integration.api:app --port 8001       # API
cd frontend && npm install && npm run dev               # dashboard on http://localhost:5173
```
Quick try in Python:
```python
from module_10_integration import CopilotAgent
a = CopilotAgent()
print(a.handle("I need tea").reply)        # asks: cafe, rest stop or reminder?
print(a.handle("a cafe").reply)            # proposes the closest cafe, asks to confirm
print(a.handle("yes").reply)               # navigates (verified)
```
The LLM parser is optional: set `GROQ_API_KEY` and use `AgentConfig(parser="llm")`. Experiments use the
rule-based parser so they are reproducible.

## Results
45 scenarios x 3 trials ([module_10_integration/RESULTS.md](module_10_integration/RESULTS.md)):

| configuration | task success | Pass^3 | questions / task | safety violations / task | hallucinated / task | constraint satisfaction | policy compliance |
|---|---|---|---|---|---|---|---|
| LLM alone | 0.09 | 0.09 | 0.00 | 0.00 | 0.98 | 0.86 | 1.00 |
| LLM + tools | 0.47 | 0.47 | 0.00 | 0.09 | 0.11 | 0.93 | 0.91 |
| + uncertainty / EVPI | 0.58 | 0.58 | 0.29 | 0.07 | 0.09 | 0.93 | 0.93 |
| + planning / CSP / search | 0.71 | 0.71 | 0.00 | 0.09 | 0.09 | 1.00 | 0.91 |
| full system (EVPI) | 1.00 | 1.00 | 0.29 | 0.00 | 0.00 | 1.00 | 1.00 |
| full system (RL policy) | 1.00 | 1.00 | 0.31 | 0.00 | 0.00 | 1.00 | 1.00 |

Route quality (chosen route time vs the A* optimum with the same stops) is 1.00 for every configuration that plans a
route. Scenario categories cover every example in the problem statement: indirect and ambiguous requests ("I need
tea", "I'm tired", "I'm running late"), internal disambiguation from calendar and contacts, conflicting appointments,
missing capabilities (massage, parking assist, lane keeping, live traffic offline), infeasible trips, soft vs strict
constraints, multi-step tasks ("a charger near my next appointment, and tell them I may be late"), changing
conditions while driving (road closure, station offline, battery draining faster than expected, destination change,
tool timeout) and unsafe actions.

- EVPI clarification: 0.983 success with 0.73 questions per dialogue, vs 1.000 / 1.10 for always-ask and 0.661 for
  never-ask ([module_4_evpi/README.md](module_4_evpi/README.md)).
- RL (state includes the driving load; reward charges for distraction and delay): Q-learning mean reward 9.60 vs
  9.27 for the best rule baseline ([module_8_rl/RESULTS.md](module_8_rl/RESULTS.md)).
- A* returns the same optimal cost as UCS on all 272 node pairs with 22-48 % fewer node expansions
  ([module_5_search/README.md](module_5_search/README.md)).

## Repository layout
```
contracts/              shared data shapes
module_1_simulator/ ... module_10_integration/
LLM connection/         module 2: earlier FastAPI NLU backend (fixed)
frontend/               React dashboard (module 10)
docs/                   module index, resources, README template, branch setup
scripts/release_check.sh
```
See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/BRANCH_SETUP.md](docs/BRANCH_SETUP.md) for the branch workflow.
