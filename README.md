# Ambiguity-Aware In-Car Copilot

A hybrid AI agent for an in-car assistant: an LLM interprets requests, classical AI modules validate and plan,
a deterministic safety layer can block actions, and only tool-confirmed outcomes are reported.
See the problem statement PDF for the full workflow.

## Modules
See [docs/MODULES.md](docs/MODULES.md) for owners, inputs/outputs and status. Each module folder has its own README
with that owner's notes.

## Repository layout
```
contracts/             shared data shapes (draft v0), used by all modules
module_4_evpi/         module 4: EVPI clarification
LLM connection/        module 2 (Arjo): NLU / LLM backend + early orchestrator
frontend/              React UI (early version)
docs/                  module index, resources, README template
```
New modules are added as `module_<n>_<name>/` folders.

## Run the tests
```bash
pip install -r requirements-dev.txt
python -m pytest
python -m module_4_evpi.demo
```
See [CONTRIBUTING.md](CONTRIBUTING.md) before pushing anything, and [docs/BRANCH_SETUP.md](docs/BRANCH_SETUP.md) for the branch strategy.
