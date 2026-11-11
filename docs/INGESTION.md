# BofA Report Ingestion

The app owns the Gmail -> PDF -> accessible HTML -> company records -> cleaned
JSON -> PostgreSQL pipeline. Parsing was adapted from BofAStockAnalysis; that
sibling project is not a runtime dependency.

## Setup and Commands

```bash
uv sync --locked
uv run python stock_analysis/manage.py migrate
```

Create private, Git-ignored `.env.bofa` using `.env.bofa.example`. Set
`GMAIL_EMAIL`, `GMAIL_APP_PASSWORD`, and optionally `GMAIL_LABEL`. Use a Google app
password and quote values containing spaces. Keep the existing email forwarding
and Gmail labeling rule active. Only the worker needs these secrets; the web
process does not. No mailbox credentials are stored in the database or forms.

Check one recent digest without writing stocks/reports or completion checkpoints:

```bash
uv run --env-file .env.bofa python stock_analysis/manage.py sync_bofa_reports --limit 1 --dry-run
```

Dry-run does create run history and private artifacts. A real sync still processes
these messages. Import once, or run a background worker alongside the web app:

```bash
uv run --env-file .env.bofa python stock_analysis/manage.py sync_bofa_reports
uv run --env-file .env.bofa python stock_analysis/manage.py ingestion_worker
```

By default the worker schedules a sync 900 seconds after the last non-dry-run run
finishes. Set `BOFA_SYNC_INTERVAL` or `--interval`; `--interval 0` processes only
manual requests. `--once` processes at most one queued/due run and exits nonzero on
failure. A new worker with scheduling enabled starts a run immediately.

The sync defaults to inspecting all UIDs, fetching only unfinished messages.
`--limit N` deliberately restricts inspection to the newest N messages and can
exclude older unfinished messages. Gmail is read-only; messages are not marked read.

Use the IDE configuration `uv ingestion_worker`, or a process manager for persistent
hosting. The worker command does not install an OS service or start with Django.
SIGINT/SIGTERM request a graceful stop after the active run.

## Staff Controls

Staff with `stocks.view_ingestionrun` see **Report sync** in the site header and
admin. Grant `stocks.add_ingestionrun` for **Sync reports** and
`stocks.view_ingestionmessage` for individual errors; superusers have these already.
The sync action is a CSRF-protected POST that queues work and returns immediately.
Repeated clicks reuse the active run. Run history and checkpoints are read-only.

The page shows worker heartbeat status, progress, counts, and errors. Refresh to
update it. Offline workers leave requests queued. Start another sync to retry a
failure; successful messages are skipped.

## Storage and Reliability

- `BOFA_INGESTION_DIR` selects persistent private storage; the default is
  `stock_analysis/ingestion_data/`, ignored by Git. Preserve it across deployments
  and never serve it publicly: research files can contain signed links. No automatic
  retention/deletion policy is installed.
- PDF SHA-256 directories contain `report.pdf`, `report.html`, cached company HTML,
  and complete validated `reports.json`. Writes use private permissions and atomic
  replacement; JSON never represents a partially extracted digest.
- Message keys include account, label, UIDVALIDITY, and UID. Completed messages
  avoid refetching; a completed PDF hash avoids re-extracting duplicate deliveries.
- Report fingerprints compare normalized fields, takeaways, and EPS, excluding
  timestamps. Identical legacy manual imports are compared too. Forwarded copies
  with changed receipt dates do not duplicate identical observations; changed
  content can still create a new timestamped observation.
- Timestamp uses the original MIME Date, including an attached forwarded email,
  with Gmail receipt time as fallback, normalized to UTC minutes. Inline forwarding
  can lose original dates; content deduplication cannot infer missing publication
  dates. Avoid mass historical re-forwarding as a backfill method.
- Every company must extract and validate before that digest imports. One database
  transaction covers its reports and completion checkpoint. Failed messages retry
  on the next sync; successful company HTML is cached. Unavailable publications
  remain failures until source access or content is corrected.
- A PostgreSQL session advisory lock excludes concurrent workers/one-shot syncs.
  Restarting a worker marks interrupted runs failed and resumes unfinished messages
  on its next run. A force-stopped process releases the lock when disconnected.
- Network requests verify TLS certificates, enforce connect/read timeouts and
  redirect limits, and allow only configured BofA hosts. Legacy HTTP
  `research1.ml.com/C` links are upgraded to HTTPS before requesting them.
  Unexpected hosts and insecure links fail explicitly.

## Manual Imports and Validation

```bash
uv run python stock_analysis/manage.py import_reports --dry-run
uv run python stock_analysis/manage.py import_reports --source /path/to/reports.json
uv run python stock_analysis/manage.py import_reports --source /path/to/json_directory
```

The default remains `stock_analysis/company_jsons`. Existing stock/timestamp rows
are skipped, never updated. Missing timestamps, invalid numbers/arrays, and model
field errors are reported and cause a nonzero exit code; valid records still import.
Dry-run validates those same fields without writes. Numbers round to model precision.

The existing CI command `uv run python stock_analysis/manage.py test stocks investor`
discovers `stocks/test_ingestion.py`, including mocked network integration, retry,
rollback, legacy deduplication, permissions/CSRF, scheduling, and a two-connection
Postgres lock test. CI requires no Gmail secrets or report downloads. Existing hooks
and workflows already cover these tests and new dependencies; no extra rules needed.

## Implementation Files

- Pipeline: `stock_analysis/stocks/ingestion/__init__.py`,
  `stock_analysis/stocks/ingestion/parsers.py`,
  `stock_analysis/stocks/ingestion/source.py`,
  `stock_analysis/stocks/ingestion/runner.py`.
- Commands/shared import: `stock_analysis/stocks/report_import.py`,
  `stock_analysis/stocks/management/commands/import_reports.py`,
  `stock_analysis/stocks/management/commands/sync_bofa_reports.py`,
  `stock_analysis/stocks/management/commands/ingestion_worker.py`.
- Persistence: `stock_analysis/stocks/models.py`,
  `stock_analysis/stocks/migrations/0002_ingestionworker_dailyreport_ingestion_fingerprint_and_more.py`.
- Staff UI: `stock_analysis/stocks/admin.py`,
  `stock_analysis/stocks/templates/base.html`,
  `stock_analysis/stocks/templates/admin/stocks/ingestionrun/change_list.html`.
- Configuration: `stock_analysis/stock_analysis/settings.py`, `pyproject.toml`,
  `uv.lock`, `.gitignore`, `.env.bofa.example`, `.run/uv ingestion_worker.run.xml`.
- Tests: `stock_analysis/stocks/test_ingestion.py`.
- Guidance: `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/CODEX_GUIDE.md`,
  `docs/DEVELOPMENT.md`, `docs/HISTORY.md`, `docs/README.md`, `docs/INGESTION.md`.

Local `.env.bofa` is private and ignored. The existing app-review documentation
and `.run/uv runserver.run.xml` configuration edit are included in this release.
