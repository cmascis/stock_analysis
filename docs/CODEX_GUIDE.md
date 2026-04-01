# Codex Guide

This file is optimized for future Codex agents. Read this first for fast orientation.

## 60-Second Overview

- This is a Django app with two first-party apps: `stocks` and `investor`.
- The home page is both marketing (anonymous users) and dashboard (authenticated users).
- Most heavy data shaping happens in `stocks/views.py` through annotations/subqueries.
- The database is PostgreSQL-only in current settings.
- Analyst report ingestion is done through `import_reports` from local JSON files.

## Where to Start by Task

- UI/dashboard changes:
  - `stock_analysis/stocks/views.py`
  - `stock_analysis/stocks/templates/stocks/home.html`
  - `stock_analysis/stocks/static/stocks/theme.css`
  - tests in `stock_analysis/stocks/tests.py`

- Search or ranking behavior:
  - `stock_analysis/stocks/views.py` (`advanced_stock_search`, helper functions)
  - `stock_analysis/stocks/templates/stocks/advanced_search.html`
  - tests in `stock_analysis/stocks/tests.py`

- Stock detail behavior/charts:
  - `stock_analysis/stocks/views.py` (`stock_detail`)
  - `stock_analysis/stocks/templates/stocks/stock_detail.html`
  - tests in `stock_analysis/stocks/tests.py`

- Auth/signup workflow:
  - `stock_analysis/investor/views.py`
  - `stock_analysis/investor/forms.py`
  - templates under `stock_analysis/investor/templates/registration/`
  - tests in `stock_analysis/investor/tests.py`

- Data model/import changes:
  - `stock_analysis/stocks/models.py`
  - `stock_analysis/investor/models.py`
  - `stock_analysis/stocks/management/commands/import_reports.py`
  - `stock_analysis/stocks/admin.py` and `stock_analysis/investor/admin.py`
  - add/update migrations

## Important Invariants

- `Stock.ticker`, `Stock.region`, and `Stock.currency_code` are normalized to uppercase.
- `DailyReport.rating` is normalized to uppercase with internal whitespace replaced by underscores.
- A report is unique per `(stock, as_of_timestamp)` (`uniq_report_as_of_timestamp_per_stock`).
- `HoldingSnapshot` is append-only by design and unique per `(user, stock, as_of)`.
- `Watch` is unique per `(user, stock)`.
- Advanced search intentionally uses latest available non-null value per metric (not always the same report row per field).

## Query/Performance Patterns Already in Use

- `Subquery + OuterRef` for latest per-stock metrics in dashboard and advanced search.
- `select_related`/`prefetch_related` on detail and admin flows.
- Deterministic ordering and tie-breakers (`ticker`, `region`) to keep UI stable.

Follow existing patterns before introducing new query shapes.

## Gotchas

- Tests require a reachable Postgres instance; app defaults point to `localhost:5432`.
- `uv run python stock_analysis/manage.py test` can report `0` tests; use explicit labels:
  - `uv run python stock_analysis/manage.py test stocks investor`
- `stock_detail.html` depends on external Chart.js CDN:
  - `https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js`
- `import_reports` reads from `stock_analysis/company_jsons/` and skips malformed records.
- `import_reports` uses `get_or_create` for reports; existing `(stock, as_of_timestamp)` rows are skipped, not updated.

## Change Checklist

When adding a new report field or metric:

1. Add model field in `stocks/models.py`.
2. Add migration.
3. Update import mapping in `import_reports.py`.
4. Update relevant view annotations/calculations in `stocks/views.py`.
5. Update template rendering.
6. Update/add tests in `stocks/tests.py`.
7. If needed, expose in admin `list_display`/filters/inlines.

When changing auth behavior:

1. Update `investor/forms.py` and `investor/views.py`.
2. Update templates in `investor/templates/registration/`.
3. Ensure URL wiring in `stock_analysis/urls.py` still aligns.
4. Update `investor/tests.py`.

## Handy Commands

```bash
docker compose up -d db
uv sync
uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite
uv run python stock_analysis/manage.py migrate
uv run python stock_analysis/manage.py runserver
uv run python stock_analysis/manage.py test stocks investor
uv run python stock_analysis/manage.py import_reports --dry-run
uv tool run prek run --all-files
uv run python scripts/uv_ci_local_validation.py
```

## High-Value Files to Read First

- `stock_analysis/stocks/views.py`
- `stock_analysis/stocks/models.py`
- `stock_analysis/investor/models.py`
- `stock_analysis/stocks/tests.py`
- `stock_analysis/investor/tests.py`
- `stock_analysis/stocks/templates/base.html`
