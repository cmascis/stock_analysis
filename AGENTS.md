# AGENTS.md

Project-specific guidance for Codex agents working in this repository.

Rule priority: if any instruction is ambiguous, default to the stricter interpretation in `Task Completion Protocol (Required Every Time)`.

## Read Order

1. `docs/CODEX_GUIDE.md` (fastest orientation)
2. `docs/ARCHITECTURE.md`
3. `docs/DEVELOPMENT.md`
4. `docs/branching-strategy.md`
5. `docs/tooling.md`
6. `docs/HISTORY.md`

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
- `DailyReport` uniqueness is `(stock, as_of_timestamp)`.
- `DailyReport.rating` is normalized to uppercase + underscore-separated tokens.
- `HoldingSnapshot` is append-only and unique per `(user, stock, as_of)`.
- `Watch` is unique per `(user, stock)`.
- Advanced search uses latest non-null value per metric, not a single shared "latest report row" for every field.

## Common Edit Surfaces

- Dashboard/search/detail logic: `stock_analysis/stocks/views.py`
- Stock templates: `stock_analysis/stocks/templates/stocks/`
- Global layout and stock quick-search JS: `stock_analysis/stocks/templates/base.html`
- Import pipeline: `stock_analysis/stocks/management/commands/import_reports.py`
- Auth/signup flow: `stock_analysis/investor/views.py`, `stock_analysis/investor/forms.py`
- Tests: `stock_analysis/stocks/tests.py`, `stock_analysis/investor/tests.py`

## When Adding a New Report Metric

1. Update `stocks/models.py` and create migration.
2. Update import mapping in `import_reports.py`.
3. Update relevant annotations/filters/order fields in `stocks/views.py`.
4. Update templates.
5. Update tests.

## Notes

- Postgres must be reachable for migrations/tests.
- `stock_detail.html` uses external Chart.js CDN.
- JSON import source directory is `stock_analysis/company_jsons/`.

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
