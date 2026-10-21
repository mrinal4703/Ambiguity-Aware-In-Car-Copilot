#!/usr/bin/env bash
# Run by the maintainer before updating main.   Usage:  bash scripts/release_check.sh
set -euo pipefail
git fetch origin --quiet

echo "== 1. main must be an ancestor of development (release is then a pure fast-forward) =="
if git merge-base --is-ancestor origin/main origin/development; then
  echo "OK"
else
  echo "FAIL: main has commits that development lacks."
  echo "Fix once:  git checkout development && git merge origin/main && git push origin development"
  exit 1
fi

echo; echo "== 2. what will change on main =="
git diff --stat origin/main origin/development | tail -n 5 || true

echo; echo "== 3. contributor branches not yet merged into development =="
for b in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin | grep -v -E '^origin(/(main|development|HEAD))?$'); do
  n=$(git rev-list --count "origin/development..$b")
  echo "$b: $n commit(s) not in development"
done

echo; echo "== 4. tests on a clean checkout of development (fresh virtualenv) =="
tmp=$(mktemp -d)
git worktree add -q --detach "$tmp" origin/development
trap 'git worktree remove --force "$tmp" >/dev/null 2>&1 || true' EXIT
(cd "$tmp" && python3 -m venv .venv-release && ./.venv-release/bin/pip install -q -r requirements-dev.txt && ./.venv-release/bin/python -m pytest -q)

echo; echo "All checks passed. To release:"
echo "  git checkout main && git pull && git merge --ff-only origin/development && git push origin main"
