# Branching Strategy

This repository uses a lightweight trunk-based model with a protected `main` target.

## Goals

- Keep `main` releasable.
- Keep changes small and reviewable.
- Avoid long-lived divergence.

## Branch model

- `main`: integration branch, always expected to pass CI.
- Topic branches: short-lived branches created from `main`.

Branch naming convention:

- `feature/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`
- `docs/<short-description>`
- `refactor/<short-description>`
- `test/<short-description>`
- `hotfix/<short-description>`
- `release/<short-description>`
- `dependabot/<ecosystem>/<dependency-and-version>` (automation exception)

## Merge strategy

- Squash merge only.
- Merge commits and rebase merges are disabled.
- Branches are auto-deleted after merge.

## Standard workflow (developers and agents)

1. Sync local `main` with remote:
   - `git switch main`
   - `git pull --ff-only origin main`
2. Create a topic branch from `main` using an allowed prefix:
   - `git switch -c <type>/<short-description>`
3. Implement changes and run local validation with `uv`:
   - `uv run python stock_analysis/manage.py check`
   - `uv run python stock_analysis/manage.py makemigrations --check --dry-run`
   - `uv run python stock_analysis/manage.py test stocks investor`
   - `uv tool run prek run --all-files`
4. Commit only on the topic branch and push:
   - `git push -u origin <type>/<short-description>`
5. Open a pull request from the topic branch into `main`.
6. Wait for required checks (`checks` and `branch-policy`) to pass.
7. Merge using squash merge.
8. Sync back to `main` for the next task:
   - `git switch main`
   - `git pull --ff-only origin main`

## Exact workflow for a new feature

Use this sequence for every net-new feature.

1. Confirm local repo is clean and sync `main`:
   - `git switch main`
   - `git pull --ff-only origin main`
   - `git status --short`
2. Ensure tooling and hooks are installed (run once per machine, then re-run if needed):
   - `uv sync`
   - `uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite`
3. Create a topic branch from `main`:
   - `git switch -c feature/<short-description>`
4. Implement the feature and update tests/docs as needed.
5. Run validations before commit:
   - `uv run python stock_analysis/manage.py check`
   - `uv run python stock_analysis/manage.py makemigrations --check --dry-run`
   - `uv run python stock_analysis/manage.py test stocks investor`
   - `uv tool run prek run --all-files`
   - Optional single-command CI-equivalent run:
     - `uv run python scripts/uv_ci_local_validation.py`
6. Commit on the topic branch:
   - `git add -A`
   - `git commit -m "Describe the feature change"`
7. Push branch and open PR to `main`:
   - `git push -u origin feature/<short-description>`
8. Complete the PR template and wait for required checks:
   - `checks`
   - `branch-policy`
9. Merge using squash merge only.
10. Sync local `main` after merge:
    - `git switch main`
    - `git pull --ff-only origin main`
    - `git branch -d feature/<short-description>`

## Required checks before merge

- CI workflow (`.github/workflows/ci.yml`)
  - Includes migration drift detection via `makemigrations --check --dry-run`.
- Branch Policy workflow (`.github/workflows/branch-policy.yml`)
- `dependabot/*` branches are explicitly allowed by Branch Policy.

## Local enforcement

Branch policy is enforced with pre-commit and pre-push hooks:

- Hook script: `scripts/check-branch-policy.sh`
- Hook registration: `uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite`
- Tooling policy: use `uv tool run prek ...` for hook and lint workflows.
- Behavior:
  - Blocks direct commits to `main`/`master`.
  - Blocks direct pushes from `main`/`master`.
  - Blocks detached-HEAD pushes.
  - Blocks detached-HEAD commits.
  - Enforces branch naming pattern for topic branches.
  - Allows `dependabot/*`.
  - Auto-skips local hook enforcement in CI where detached `HEAD` is expected.
- Emergency bypass:
  - `ALLOW_MAIN_COMMIT=1 git commit ...`
  - `ALLOW_MAIN_PUSH=1 git push`
  - Use only for intentional, exceptional maintenance events.

## Expected policy behavior

- Direct commits to `main` are blocked locally by `scripts/check-branch-policy.sh` and remotely by branch protection.
- Direct pushes to `main` are blocked locally and remotely.
- If a commit or push is blocked because you are on `main`, create/switch to a valid topic branch and retry.
- Valid topic branch prefixes are:
  - `feature/`
  - `fix/`
  - `chore/`
  - `docs/`
  - `refactor/`
  - `test/`
  - `hotfix/`
  - `release/`

## GitHub settings automation

Apply merge policy and branch protection defaults with:

- `scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --dry-run`
- `scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --apply`
