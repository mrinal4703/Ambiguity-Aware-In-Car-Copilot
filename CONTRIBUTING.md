# Contributing

## Branches
- `main`: final release only. Only the maintainer (Mrinal) updates it, by fast-forwarding from `development`.
- `development`: where everyone's work is integrated. Nobody pushes here directly.
- Your own branch (named after you): where you work.

## Rules
1. Work only on your own branch. Never push to `main` or `development`.
2. Keep your code in your own module folder. Use underscores so it can be imported:
   `module_1_simulator/`, `module_3_uncertainty/`, `module_5_search/` ...
   Put an `__init__.py` in the folder and in its `tests/` folder.
3. Do not edit another module's files. Need a change? Message the owner, or open a PR they review.
4. Shared data shapes live in `contracts/`. Changing them affects everyone: open a PR and announce it in the group.
5. Never commit `.env`, API keys, `__pycache__`, `node_modules` or `.venv`.
6. Every module needs: code, tests, and a `README.md` (use `docs/MODULE_README_TEMPLATE.md`).

## Weekly routine
```bash
git checkout <your-branch>
git fetch origin
git merge origin/development      # bring in everyone else's latest work
# ... work in your folder, commit ...
python -m pytest                  # tests must pass
git push origin <your-branch>
```
Then open a Pull Request: **your branch -> development** (check the base branch!). The maintainer reviews and merges.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

## Commit messages
Short and specific: `module 5: add A* with energy cost` (not `update`).
