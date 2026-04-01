# Development Workflow

## Prerequisites

- Docker (for local Postgres)
- `uv`
- Python compatible with `pyproject.toml` (`>=3.14`)

This is a strict `uv` project. Do not use `pip` or `python -m pip`.

## First-Time Setup

1. Start DB:

   ```bash
   docker compose up -d db
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Apply migrations:

   ```bash
   uv run python stock_analysis/manage.py migrate
   ```

4. Start app:

   ```bash
   uv run python stock_analysis/manage.py runserver
   ```

## Running Tests

Preferred command:

```bash
uv run python stock_analysis/manage.py test stocks investor
```

Note:

- Running without app labels can return `Found 0 test(s)` in this project layout.
- Tests require a running Postgres instance.

## Guardrails and CI

### Install local hooks and tooling

```bash
./scripts/bootstrap_dev_guardrails.sh
```

This installs `prek` git hooks for both `pre-commit` and `pre-push`.

### Run the same checks as CI

```bash
./scripts/run_local_ci.sh
```

This script performs:

1. `prek` pre-commit checks (including `ruff` and file hygiene)
2. migration drift check
3. migrations apply
4. Django tests (`stocks`, `investor`)

### Branch and PR contract

- Branch naming:
  - `feature/<slug>`
  - `fix/<slug>`
  - `chore/<slug>`
  - `docs/<slug>`
- `main` is PR-only and protected.
- Merge policy is squash-only.
- Required GitHub checks:
  - `lint`
  - `migrations`
  - `tests`

### Apply repository guardrails programmatically

```bash
./scripts/apply_github_guardrails.sh --dry-run
./scripts/apply_github_guardrails.sh --apply
```

## Data Flows

### Load fixture snapshot

```bash
uv run python stock_analysis/manage.py loaddata mysite_data.json
```

### Export fixture snapshot

```bash
uv run python stock_analysis/manage.py dumpdata auth.user investor stocks --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude admin.logentry --exclude sessions --indent=2 --output=mysite_data.json
```

### Import JSON reports

Put source files in:

- `stock_analysis/company_jsons/`

Then run:

```bash
uv run python stock_analysis/manage.py import_reports
```

Dry run:

```bash
uv run python stock_analysis/manage.py import_reports --dry-run
```

## Environment Variables

Configured in `stock_analysis/stock_analysis/settings.py`.

- `POSTGRES_DB` (default `stock_analysis`)
- `POSTGRES_USER` (default `stock_analysis`)
- `POSTGRES_PASSWORD` (default `stock_analysis`)
- `POSTGRES_HOST` (default `localhost`)
- `POSTGRES_PORT` (default `5432`)
- `ALLOWED_HOSTS` comma-separated (default `localhost,127.0.0.1,0.0.0.0`)

## Common Task Recipes

### Add a field to `DailyReport`

1. Update model in `stock_analysis/stocks/models.py`.
2. Create migration:

   ```bash
   uv run python stock_analysis/manage.py makemigrations
   ```

3. Apply migration:

   ```bash
   uv run python stock_analysis/manage.py migrate
   ```

4. Update importer (`import_reports.py`) if field comes from source JSON.
5. Update views/templates/tests where displayed or filtered.

### Adjust advanced search behavior

1. Update constants/helpers in `stock_analysis/stocks/views.py`:
   - `NUMERIC_FILTER_CONFIG`
   - `SORT_FIELD_CHOICES`
   - `SORT_FIELD_MAP`
   - ordering/filter helpers
2. Update `stock_analysis/stocks/templates/stocks/advanced_search.html`.
3. Update tests in `stock_analysis/stocks/tests.py`.

### Adjust dashboard cards

1. Update helper builders in `stock_analysis/stocks/views.py`.
2. Update `stock_analysis/stocks/templates/stocks/home.html`.
3. Update tests in `stock_analysis/stocks/tests.py`.

## Admin

- Stocks/admin config:
  - `stock_analysis/stocks/admin.py`
- Investor/admin config:
  - `stock_analysis/investor/admin.py`

Use admin for quick data verification during development.
