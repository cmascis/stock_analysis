# Stock Analysis

Server-rendered Django application for tracking stocks, analyst reports, investor holdings, and watchlists.

## What It Does

- Imports analyst report JSON into PostgreSQL.
- Serves a home page that is marketing for anonymous users and a dashboard for authenticated users.
- Provides stock quick search, advanced latest-metric search, and stock detail timelines.
- Tracks investor watchlists and append-only holding snapshots.

## Stack

- Python `>=3.14` (managed with `uv`)
- Django `6.0.x` monolith with apps `stocks` and `investor`
- PostgreSQL `17` (local Docker service supported)
- Server-rendered templates + small vanilla JS enhancements

## Project Layout

- `stock_analysis/manage.py`: Django management entrypoint
- `stock_analysis/stock_analysis/`: Django project config (`settings.py`, root `urls.py`)
- `stock_analysis/stocks/`: stock/report domain models, views, templates, import command
- `stock_analysis/investor/`: investor profile, watchlist/holdings models, signup/auth wiring
- `stock_analysis/company_jsons/`: local JSON source files for `import_reports`
- `scripts/`: validation, branch-policy, and GitHub guardrail helpers
- `docs/`: onboarding, architecture, workflow, and tooling references
- `docker-compose.yml`: local Postgres service

## Quick Start

1. Start PostgreSQL:

   ```bash
   docker compose up -d db
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Run migrations:

   ```bash
   uv run python stock_analysis/manage.py migrate
   ```

4. (Optional) load a previously exported fixture snapshot if you have one locally:

   ```bash
   uv run python stock_analysis/manage.py loaddata mysite_data.json
   ```

   The repository does not currently ship a `mysite_data.json` file.

5. Run dev server:

   ```bash
   uv run python stock_analysis/manage.py runserver
   ```

## Local Configuration

Environment variables are read in `stock_analysis/stock_analysis/settings.py`.

- `POSTGRES_DB` default `stock_analysis`
- `POSTGRES_USER` default `stock_analysis`
- `POSTGRES_PASSWORD` default `stock_analysis`
- `POSTGRES_HOST` default `localhost`
- `POSTGRES_PORT` default `5432`
- `ALLOWED_HOSTS` default `localhost,127.0.0.1,0.0.0.0`

## Data Import

The custom command `import_reports` reads JSON files from:

- `stock_analysis/company_jsons/*.json`

Run:

```bash
uv run python stock_analysis/manage.py import_reports
```

Dry run:

```bash
uv run python stock_analysis/manage.py import_reports --dry-run
```

## Tests

Use app labels so Django discovers this project test suite consistently:

```bash
uv run python stock_analysis/manage.py test stocks investor
```

Tests require a reachable Postgres instance.

## CI and Guardrails

This repository uses `prek` + `ruff` guardrails locally and in GitHub Actions.

1. Install local hooks:

   ```bash
   uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite
   ```

2. Run the full local CI equivalent:

   ```bash
   uv run python scripts/uv_ci_local_validation.py
   ```

3. Preview or apply GitHub guardrail settings:

   ```bash
   scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --dry-run
   scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --apply
   ```

Required checks on pull requests to `main`:

- `checks`
- `branch-policy`

See `docs/branching-strategy.md` and `docs/tooling.md` for branch naming and day-to-day workflow.
Use `docs/branching-strategy.md` section `Exact workflow for a new feature` as the canonical start-to-merge checklist.

## Codex-Focused Documentation

- `docs/CODEX_GUIDE.md`: fastest onboarding path for future Codex agents
- `docs/ARCHITECTURE.md`: data model, request flow, and query patterns
- `docs/DEVELOPMENT.md`: practical local workflows and operational commands
- `docs/tooling.md`: canonical `uv` and validation command usage
- `docs/documentation-policy.md`: rules for keeping agent and developer docs current
- `docs/HISTORY.md`: implementation timeline distilled from git history
