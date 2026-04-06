# Development Workflow

## Prerequisites

- Docker (for local Postgres)
- `uv`
- Python compatible with `pyproject.toml` (`>=3.14`)

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
- Run `uv run python stock_analysis/manage.py check` and `uv run python stock_analysis/manage.py makemigrations --check --dry-run` alongside tests before closing implementation work.

## Guardrails and CI

### Install local hooks and tooling

```bash
uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite
```

This installs `prek` git hooks for both `pre-commit` and `pre-push`.

### Run the same checks as CI

```bash
uv run python scripts/uv_ci_local_validation.py
```

This command performs:

1. `docker compose up -d db`
2. `uv sync --locked`
3. `uv run python stock_analysis/manage.py check`
4. `uv run python stock_analysis/manage.py makemigrations --check --dry-run`
5. `uv run python stock_analysis/manage.py test stocks investor`
6. `uv tool run prek run --all-files --show-diff-on-failure`

### Branch and PR contract

- Branch naming:
  - `feature/<slug>`
  - `fix/<slug>`
  - `chore/<slug>`
  - `docs/<slug>`
  - `refactor/<slug>`
  - `test/<slug>`
  - `hotfix/<slug>`
  - `release/<slug>`
- `main` is PR-only and protected by policy.
- Merge policy is squash-only.
- Required GitHub checks:
  - `checks`
  - `branch-policy`

### Apply repository guardrails programmatically

```bash
scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --dry-run
scripts/apply_github_guardrails.sh --repo cmascis/stock_analysis --branch main --apply
```

## Data Flows

### Load fixture snapshot

If you already have an exported snapshot locally:

```bash
uv run python stock_analysis/manage.py loaddata mysite_data.json
```

The repository does not currently include a committed `mysite_data.json` file.

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

### Update documentation after new findings

1. Put durable agent guidance in `AGENTS.md`.
2. Put topic-specific detail in the smallest canonical doc under `docs/`.
3. Correct stale command examples or missing file references immediately when discovered.
4. Update `README.md` too if the change affects local setup or day-to-day workflows.

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

### Adjust header search behavior

1. Update `stock_analysis/stocks/views.py` (`stock_search_suggestions`) if query or ranking behavior changes.
2. Update the inline search UI in `stock_analysis/stocks/templates/base.html`.
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

## Run Configurations

The `.run/` directory includes IDE run configs for common `uv` workflows such as `runserver`, `migrate`, `makemigrations`, `import_reports`, fixture load/dump, `prek`, and local CI validation.
