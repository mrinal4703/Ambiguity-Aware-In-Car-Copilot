# Module 8: Reinforcement learning   (owner: Jana)

## What this module does
Learns when to execute, look up context, ask, confirm, refuse or offer an alternative. A tabular Q-learning agent is
trained in a simulated decision MDP and compared with four baselines, all behind the same safety gate.

## Inputs and outputs
- Takes in: belief features from module 4 (`belief_features`) + state flags (risk, resolvable context, capability).
- Hands on: one of six actions (EXECUTE, GATHER_CONTEXT, CLARIFY, DELAY, SUGGEST_ALTERNATIVE, REFUSE). Used by module 10
  when `policy="rl"`.

## How to run / test
```bash
python -m pytest module_8_rl
python -m module_8_rl.evaluate        # trains, evaluates, writes RESULTS.md
```

## Design notes
- Rewards from the PDF: +10 success, +2 useful clarification, -2 unnecessary question, -5 wrong action,
  -20 unsafe, -20 hallucinated success; sensitivity variants in `reward.py`.
- The safety mask is applied in training and evaluation alike (unsafe actions are replaced by the gate fallback).
- Epsilon decays automatically over training; discretised feature state.

## Results
Full tables in [RESULTS.md](RESULTS.md).

| policy | mean reward | success |
|---|---|---|
| always_execute | 6.13 | 0.771 |
| always_clarify | 5.56 | 0.865 |
| fixed_threshold | 7.57 | 0.865 |
| evpi | 7.57 | 0.871 |
| hybrid_rules | 9.27 | 0.984 |
| q_learning | 9.60 | 0.979 |

With the distraction cost the learned policy asks less when driving is demanding (0.28 vs 0.32 of situations).

Finding: because a useful clarification earns +2 while a context lookup costs -0.5, the learned policy sometimes asks
a question that a lookup would have answered (seen in module 10's `ctx_rahul_meeting` scenario). This is a property
of the specified reward, not a bug; a lookup bonus would remove it.

## State and reward (problem-statement review)
The state now includes the vehicle and driving context (driving difficulty low / medium / high, battery low) next to
the intent belief, feasibility, tool support and interaction history (remaining question budget = questions already
asked, context already used). The reward adds a distraction cost (-1.5) for asking while driving is demanding and a
delay cost (-0.3) per extra turn, as the PDF asks ("penalize ... distraction, or delay"). Training: 150k episodes.

## Known limitations / TODO
- [ ] Tabular state; a function approximator would be needed for richer features.

## Log (newest first)
- 2026-10-28 (problem-statement review): driving-context state, distraction and delay costs, retrained (150k episodes); 10 tests.
- 2026-10-28: MDP, rewards, Q-learning, baselines, evaluation and sensitivity analysis; 9 tests.
