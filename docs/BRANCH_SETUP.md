# Branch strategy and one-time GitHub setup

```
your-branch ──PR──▶ development ──(final release by Mrinal)──▶ main
 (each person)      (integration; tests must pass)             (only the verified result)
```

- Contributors never touch `main`.
- `development` is the working integration branch: PRs need the tests to pass and one approval.
- `main` only ever receives a fast-forward of `development`, done by the maintainer after `scripts/release_check.sh` passes.
  Because it is a fast-forward, `main` ends up byte-for-byte identical to `development`: the final merge changes nothing.

## One-time GitHub settings (maintainer)
1. Settings -> Branches -> **Default branch** -> `development`. PRs and clones then target it by default.
2. Settings -> Rules -> Rulesets -> New branch ruleset **protect-development** (target: `development`):
   - Restrict deletions; Block force pushes
   - Require a pull request before merging: 1 approval, dismiss stale approvals, require conversation resolution
   - Require status checks: `pytest` (it appears in the list after the workflow has run once), and "require branches to be up to date"
3. New branch ruleset **protect-main** (target: `main`):
   - Restrict deletions; Block force pushes; Restrict updates
   - Bypass list: Repository admin (so you can push the final fast-forward)
   - Optional, if you prefer releasing through a PR: require a PR plus the checks `only-from-development` and `tests`
4. Settings -> Actions -> General: make sure workflows are allowed to run.
5. Solo approvals: you cannot approve your own PR. Either keep yourself on the bypass list for `development` or ask a second person to approve your PRs.

If the repository is private on a free plan, GitHub may not offer branch protection; options are making the repo public,
using a plan that includes it (for example via the GitHub Student Developer Pack), or relying on the process alone.

## Release routine (maintainer)
```bash
bash scripts/release_check.sh          # branch sync, diff, unmerged branches, tests on a clean checkout
git checkout main && git pull
git merge --ff-only origin/development
git push origin main
```
Do not merge `development` into `main` through the GitHub "Merge pull request" button for the final release unless you want the extra merge commit; if you do, merge `main` back into `development` afterwards so the branches stay aligned.

## Before the very first release
`main` currently contains a merge commit that `development` lacks. Align them once:
```bash
git checkout development && git pull
git merge origin/main
git push origin development     # via PR if development is already protected
```

## Notes
- `scripts/release_check.sh` is a bash script. On Windows run it in WSL; in Git Bash the virtualenv path inside the script may need `Scripts/` instead of `bin/`.
- Check 1 of the script fails right now on the real repo because of the extra merge commit on `main` (see "Before the very first release"). That is the script working as intended.
