# Module 9: Safety and policy   (owner: Nishkarsh)

## What this module does
A deterministic layer, independent of the LLM, that can block any action. It checks capability (does the tool and
car feature exist), parameters, preconditions, authorisation and driving context, demands confirmation for
consequential actions, and verifies tool results before success is reported.

## Inputs and outputs
- Takes in: a candidate tool call or plan step, vehicle / driving context (`SafetyContext`).
- Hands on: `contracts.safety.SafetyVerdict` (allow / confirm / defer / block + reason; unsupported features come with an alternative).
  `verify_outcome` checks the state after a tool call.

## How to run / test
```bash
python -m pytest module_9_safety
```

## Design notes
- Capability: unsupported features (seat massage, sunroof, ...) are refused with an alternative from `ALTERNATIVES`.
- Rules, in order: capability -> missing / unresolved parameters (defer) -> validity (AC 16-30 C, window 0-100 %)
  -> driving safety (windows deferred above the speed limit, confirmation in rain, video only while parked)
  -> authorisation (known contact, contact accepts messages, recipient confidence) -> workload (non-urgent calls and
  messages deferred when driving difficulty is high) -> confirmation.
- Confirmation: messages, calls, and navigation that was inferred or adds waypoints (station names shown).
- Verification: success is reported only if the environment state actually changed as intended.

## Known limitations / TODO
- [ ] Rules are hand-written; thresholds are illustrative.

## Log (newest first)
- 2026-10-28: capability checker, policy engine, verifier; 18 tests.
