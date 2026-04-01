# Stock Analysis

Server-rendered Django application for tracking stocks, analyst reports, investor holdings, and watchlists.

## Stack

- Python `>=3.14` (managed with `uv`)
- Django `6.0.x`
- PostgreSQL `17` (local Docker service supported)
- Server-rendered templates + small vanilla JS enhancements

## Project Layout

- `stock_analysis/manage.py`: Django management entrypoint
- `stock_analysis/stock_analysis/`: Django project config (`settings.py`, root `urls.py`)
- `stock_analysis/stocks/`: stock/report domain models, views, templates, import command
- `stock_analysis/investor/`: investor profile, watchlist/holdings models, signup/auth wiring
- `docker-compose.yml`: local Postgres service
- `mysite_data.json`: optional fixture snapshot

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

4. (Optional) load fixture data:

   ```bash
   uv run python stock_analysis/manage.py loaddata mysite_data.json
   ```

5. Run dev server:

   ```bash
   uv run python stock_analysis/manage.py runserver
   ```

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

## CI and Guardrails

This repository uses `prek` + `ruff` locally and in GitHub Actions.

1. Bootstrap local guardrails:

   ```bash
   ./scripts/bootstrap_dev_guardrails.sh
   ```

2. Run the full local CI equivalent:

   ```bash
   ./scripts/run_local_ci.sh
   ```

3. Apply GitHub repo guardrails (branch protection + merge policy):

   ```bash
   ./scripts/apply_github_guardrails.sh --dry-run
   ./scripts/apply_github_guardrails.sh --apply
   ```

Required checks on `main`:

- `CI / lint`
- `CI / migrations`
- `CI / tests`

See `CONTRIBUTING.md` for branch naming and PR workflow.

## Codex-Focused Documentation

- `docs/CODEX_GUIDE.md`: fastest onboarding path for future Codex agents
- `docs/ARCHITECTURE.md`: data model, request flow, and query patterns
- `docs/DEVELOPMENT.md`: practical local workflows and operational commands
- `docs/HISTORY.md`: implementation timeline distilled from git history
