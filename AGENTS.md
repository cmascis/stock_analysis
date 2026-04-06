# AGENTS.md

Project-specific guidance for Codex agents working in this repository.

Rule priority: if any instruction is ambiguous, default to the stricter interpretation in `Task Completion Protocol (Required Every Time)`.

## Read Order

1. `docs/CODEX_GUIDE.md` (fastest orientation)
2. `docs/ARCHITECTURE.md`
3. `docs/DEVELOPMENT.md`
4. `docs/tooling.md`
5. `docs/branching-strategy.md`
6. `docs/documentation-policy.md`
7. `docs/HISTORY.md`

## Architecture Snapshot

- This is a server-rendered Django monolith with two first-party apps: `stocks` and `investor`.
- Most application behavior lives in function views and templates, especially `stock_analysis/stocks/views.py`.
- There is no active REST API namespace or separate service layer in the current codebase.
- The database backend is PostgreSQL-only in current settings; local and CI workflows assume Postgres is reachable.
- Analyst report ingestion is file-based through `stock_analysis/stocks/management/commands/import_reports.py`, reading `stock_analysis/company_jsons/*.json`.

## Key Entry Points

- `stock_analysis/manage.py`: Django management entrypoint
- `stock_analysis/stock_analysis/settings.py`: runtime configuration and environment variables
- `stock_analysis/stock_analysis/urls.py`: root routing
- `stock_analysis/stocks/urls.py`: main product routes
- `stock_analysis/stocks/views.py`: dashboard, search suggestions, stock detail
- `stock_analysis/investor/views.py`: signup flow

## Core Commands

```bash
docker compose up -d db
uv sync
uv tool run prek install --hook-type pre-commit --hook-type pre-push --overwrite
uv run python stock_analysis/manage.py migrate
uv run python stock_analysis/manage.py runserver
uv run python stock_analysis/manage.py test stocks investor
uv run python scripts/uv_ci_local_validation.py
```

## Important Project Invariants

- `Stock` identity is `(ticker, region)` and both are normalized uppercase.
- `Stock.currency_code` is normalized uppercase.
- `DailyReport` uniqueness is `(stock, as_of_timestamp)`.
- `DailyReport.rating` is normalized to uppercase + underscore-separated tokens.
- `HoldingSnapshot` is append-only and unique per `(user, stock, as_of)`.
- `Watch` is unique per `(user, stock)`.
- `InvestorProfile` is auto-created on user creation via `investor.signals`.
- Dashboard holdings/watchlist use latest non-null report values per metric, not a single shared "latest report row" for every field.
- `import_reports` skips existing duplicate `(stock, as_of_timestamp)` reports rather than updating them.

## Common Edit Surfaces

- Dashboard/search/detail logic: `stock_analysis/stocks/views.py`
- Stock templates: `stock_analysis/stocks/templates/stocks/`
- Global layout and stock quick-search JS: `stock_analysis/stocks/templates/base.html`
- Stock theme/CSS: `stock_analysis/stocks/static/stocks/theme.css`
- Import pipeline: `stock_analysis/stocks/management/commands/import_reports.py`
- Auth/signup flow: `stock_analysis/investor/views.py`, `stock_analysis/investor/forms.py`
- Investor lifecycle hook: `stock_analysis/investor/signals.py`
- Tests: `stock_analysis/stocks/tests.py`, `stock_analysis/investor/tests.py`
- CI and guardrails: `.github/workflows/`, `.pre-commit-config.yaml`, `scripts/`

## Query and UI Patterns

- Prefer the existing `Subquery + OuterRef` pattern for latest-per-stock metrics.
- Preserve deterministic ordering and tie-breakers such as `ticker` and `region`.
- Prefer `select_related`/`prefetch_related` when extending detail/admin flows.
- The frontend is server-rendered HTML with small inline JavaScript helpers; do not assume a JS build pipeline exists.

## When Adding a New Report Metric

1. Update `stock_analysis/stocks/models.py` and create migration.
2. Update import mapping in `stock_analysis/stocks/management/commands/import_reports.py`.
3. Update relevant annotations/filters/order fields in `stock_analysis/stocks/views.py`.
4. Update templates.
5. Update tests.

## Notes

- Postgres must be reachable for migrations/tests.
- Django test discovery can return `0` tests without app labels; prefer `uv run python stock_analysis/manage.py test stocks investor`.
- The repository does not currently include `mysite_data.json`; treat load/dump fixture commands as optional local workflow, not a guaranteed repo file.
- `stock_detail.html` uses external Chart.js CDN.
- JSON import source directory is `stock_analysis/company_jsons/`.
- `djangorestframework` is installed but there is no active DRF API surface in the current codebase.
- `django-debug-toolbar` is present only as commented-out config in `settings.py` and `urls.py`.
- Branch policy blocks direct commits/pushes from `main`; use a topic branch for normal implementation work.

## Task Completion Protocol (Required Every Time)

Before marking any task as complete, the agent MUST perform all applicable steps below:

1. Validation first:
   - Run the most relevant verification command(s) for the change (tests, migrations check, or targeted command).
   - Never claim success without either passing verification or explicitly reporting why verification could not run.

2. No silent failures:
   - If any command fails, include the exact command, the failure reason, and the concrete next fix attempt.
   - Do not hide skipped checks.

3. Scope check:
   - Review `git status --short` and ensure only intended files were changed.
   - If unexpected file changes are found, stop and call them out explicitly.

4. Final response contract:
   - List changed files.
   - State what was verified and the result.
   - State any remaining risk or follow-up required.
   - If verification was not possible, include exact blocker and how to unblock.

5. Behavior safety:
   - Preserve existing behavior unless the user requested a behavior change.
   - When behavior changes intentionally, explicitly call out what changed.

6. Documentation hygiene:
   - If commands/workflows/architecture changed, update docs in the same task (`README.md` and/or `docs/*`).

These rules are mandatory for every completed task in this repository.
