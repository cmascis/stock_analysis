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

## GitHub settings automation

Apply merge policy and branch protection defaults with:

- `scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --dry-run`
- `scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --apply`
