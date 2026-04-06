# Tooling and Commands

Canonical reference for environment setup, command invocation, and local validation tooling.
For the full branch/PR lifecycle, use `docs/branching-strategy.md` section `Exact workflow for a new feature`.

## Tooling policy

- Use `uv` for everything possible.
  - Project/runtime commands: `uv run ...`
  - External tools: `uv tool run ...`
- There is no active Node/npm toolchain in the current repository.
- Do not activate the virtual environment manually.
- Do not call `.venv/bin/python`, `pip`, or `python -m pip` directly for project workflows.

## Environment setup

Run from repository root (`/Users/chrismascis/stock_analysis`):

```bash
docker compose up -d db
uv sync
uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite
```

## Django command patterns

```bash
uv run python stock_analysis/manage.py <command>
```

Common commands:

```bash
uv run python stock_analysis/manage.py runserver
uv run python stock_analysis/manage.py makemigrations
uv run python stock_analysis/manage.py migrate
uv run python stock_analysis/manage.py test stocks investor
uv run python stock_analysis/manage.py import_reports --dry-run
```

## Validation commands

```bash
uv run python stock_analysis/manage.py check
uv run python stock_analysis/manage.py makemigrations --check --dry-run
uv run python stock_analysis/manage.py test stocks investor
uv tool run prek run --all-files
```

Validation notes:

- Run `uv tool run prek run --all-files` from a topic branch.
- For CI-style local validation from any branch (including `main`), run:
  - `uv run python scripts/uv_ci_local_validation.py`
- Use targeted commands when possible, but do not skip `check`, migration drift validation, or relevant tests for real changes.

## Hook and CI alignment

- Hooks are managed by `prek` via `.pre-commit-config.yaml`.
- Local branch-policy enforcement runs in pre-commit and pre-push stages via `scripts/check-branch-policy.sh`.
- Helper wrappers in `scripts/` mirror common tool invocations:
  - `uv_ci_local_validation.py`
  - `uv_prek_all.py`
  - `uv_prek_prepush.py`
- CI workflow (`.github/workflows/ci.yml`) uses:
  - `uv sync --locked`
  - `uv run python stock_analysis/manage.py check`
  - `uv run python stock_analysis/manage.py makemigrations --check --dry-run`
  - `uv run python stock_analysis/manage.py test stocks investor`
  - `uv tool run prek run --all-files --show-diff-on-failure`

## Feature-change checklist

For each feature PR, review and update as needed:

- `.github/workflows/` for CI coverage of new behavior.
- `.pre-commit-config.yaml` for local quality guardrails.
- Test suites for behavior coverage.
- `.run/` for new common run/validation workflows.
- `scripts/` for repeatable commands that should not be manual.
- `README.md`, `AGENTS.md`, and `docs/` when workflows or architecture knowledge changed.

If no updates are needed in a category, note that in the PR.
