# Implementation History

This timeline summarizes major milestones from local git history.

## Chronological Timeline

- `2026-01-31` `9508f4f`
  - Initial `uv` Python project setup.

- `2026-01-31` `1f5da42`
  - Django project scaffold plus initial `stocks` app.

- `2026-02-01` `5968c90`, `feccee1`
  - Initial stock/report schema and migration.
  - Admin registration for core models.

- `2026-02-02` `ae467ca`
  - Added `import_reports` management command for JSON analyst report ingestion.

- `2026-02-02` `9049771`, `b9e0c5c`
  - Added `investor` app and profile model.
  - Introduced signup/login/logout and home page flow.

- `2026-02-20` to `2026-02-27` `6327f1c`, `5fa4c16`, `08fb9ac`
  - Added run configurations and fixture/data command workflow cleanup.
  - Fixed user-profile signal behavior.

- `2026-03-15` `20709be`, `f4afa5a`, `9df57a2`
  - Enabled startup routing refinements.
  - Dockerized local Postgres workflow and simplified to DB-only container setup.

- `2026-03-15` `84cbfd3`, `3efc93b`, `8643ba4`
  - Completed auth UX workflow and major visual theme upgrade.
  - Added home dashboard sections and analytics cards for authenticated users.

- `2026-03-16` `f33d6e3`, `6fad2b7`, `7513570`
  - Added stock detail page, report timeline, charting, and richer formatting.
  - Added objective/price chart improvements and UI polish.

- `2026-03-16` `30b6f02`
  - Introduced stock search endpoint and full advanced search workbench:
    - text + numeric filters
    - multi-priority sorting
    - query priority display
    - pagination and latest-metric annotations

- `2026-04-02` `bb88237` (PR #11)
  - Added per-metric report provenance to the dashboard and removed leaders filtering.

- `2026-04-06` `57243ae`, `14d0201` (PR #13, PR #14)
  - Removed advanced search; quick stock suggestions remain available.
  - Refined detail metrics, rating changes, objective coverage, and chart continuation.

## App Review: November 8, 2026

This is a point-in-time assessment of commit `14d0201`, not a release certification.
GitHub comparison confirmed local HEAD matched remote `main` during the review.

### Current State

- The existing local app on port 8000 and its PostgreSQL container were running.
- Read-only database inspection found 1,746 stocks and 17,136 reports across 575
  local JSON files. Report dates span June 25, 2024 through November 6, 2026.
- Quick search, stock detail charts, report navigation, authentication, dashboard
  display, and file ingestion form a working research-app foundation.
- Holdings and watchlists have models and dashboard displays, but no ordinary-user
  management routes/forms. A non-staff user sees an Admin link that leads to an
  authorization message rather than a way to populate their dashboard.
- [Draft PR #15](https://github.com/cmascis/stock_analysis/pull/15) adds a stock
  detail analysis window. It is open, unmerged, and was not tested in this review.
- Two additional open PRs update GitHub Actions: #16 (checkout) and #17
  (setup-python). Their checks were not evaluated and nothing was merged.

### Findings and Next Work

1. Correct valuation currency and completeness before extending portfolio features.
   `home()` sums raw position values across currencies and substitutes zero for
   unavailable values. The source database has 89 non-USD stocks across 12 other
   currencies, while templates and charts hard-code dollar symbols. A QA portfolio
   with USD and AUD holdings displayed a single combined dollar total. A synthetic
   holding with ten shares and no price produced a zero total. Group totals by
   currency until an explicit FX policy exists, and label incomplete valuations.
2. Add user-facing watch/unwatch and holding-snapshot forms with ownership checks,
   then useful empty-state actions. Only show the Admin navigation item to staff.
   Retain snapshot history when positions are changed or closed.
3. Fix report-leader event selection. `_build_window_summary()` selects one latest
   eligible report per stock before comparing objectives. In isolated QA, objectives
   of 100, 150, 150 (the latter two inside the selected week) produced no upgrade.
   Evaluate changes within the whole window; define whether the card represents
   the largest individual change or a net change over the period.
4. Normalize metric presentation. AAPL's headline upside displayed 9.40%, while its
   report card displayed 0.0940. Label prices as reported prices and add freshness
   cues: NVDA's latest price/objective were dated September 3 while its latest
   rating/report were dated November 3. Preserve per-metric provenance.
5. Define active versus closed holdings. A latest zero-quantity snapshot remained
   visible and counted as a holding in QA. Also enforce the documented append-only
   convention: the current admin allows editing and deleting existing snapshots.
6. Harden ingestion and add importer regression coverage. All current source files
   parsed successfully, but a synthetic `Price: "N/A"` aborted dry-run with
   `decimal.InvalidOperation`. Missing timestamps resolve to the current time on
   every parse, defeating repeat-import deduplication. Dry-run does not execute
   model/database validation. Reject or quarantine invalid records, count errors,
   and make report identity deterministic. Existing tests do not cover imports.
7. Prepare deployment settings before exposing the app. `check --deploy` reported
   six warnings: DEBUG, the built-in insecure secret key, HTTPS redirect, HSTS,
   secure session cookies, and secure CSRF cookies. The checked-in runtime is a
   development setup; deployment and restore readiness were not established.
8. Improve mobile density after the correctness and workflow work. At 390px, the
   dashboard stayed within the viewport, but its holdings table was 920px wide
   inside a 324px scrolling container, and summary cards stacked vertically.
   Preserve the current visual design while making portfolio scanning easier.

Recommended order: valuation/presentation fixes and regression tests; watchlist
and holdings workflows; then review and finish PR #15. Deployment hardening is a
gate before any public release. Review the two dependency PRs separately.

### Verification and Boundaries

- `uv run --locked python stock_analysis/manage.py check`: passed.
- `uv run --locked python stock_analysis/manage.py makemigrations --check --dry-run`:
  no changes detected.
- `POSTGRES_DB=stock_analysis_review_20261108 uv run --locked python stock_analysis/manage.py test stocks investor --noinput`:
  all 18 tests passed in a separate test database, which Django destroyed.
- `uv run --locked python stock_analysis/manage.py import_reports --dry-run`:
  parsed all 17,136 records with no reported parse errors; no records written.
- `uv run --locked python stock_analysis/manage.py check --deploy`: completed with
  the six warnings listed above. Ordinary system checks do not imply deployment
  readiness.
- Browser checks covered anonymous home, quick search, AAPL chart and report
  navigation, and signed-in QA dashboard/login/logout/admin authorization at
  desktop size and 390px width. No chart-page console warnings/errors were captured.
- Signed-in browser checks and synthetic reproductions used a disposable database
  with four copied stocks / 313 reports and synthetic accounts/positions. Human
  account and position data were not copied or modified. The reference database
  was inspected read-only. Temporary QA server/database were removed afterward.
- Cleanup initially hit sandbox restrictions on `ps -p 7476 -o command=` and
  `os.kill(7476, signal.SIGTERM)`. A retry with elevated execution verified the
  dedicated port 8011 listener, stopped that process, and removed only the
  generated QA database successfully.
- Full hook/lint validation, load testing, backup restoration, external source-link
  access, and deployed-environment verification were not performed. No application
  code was changed by this assessment.

## Automated Report Ingestion: November 11, 2026

- Added an application-owned Gmail/PDF/HTML/JSON pipeline, a one-shot
  `sync_bofa_reports` command, and `ingestion_worker` for queued and periodic runs.
- Added read-only staff run history and message checkpoints, a permission-checked
  **Sync reports** action, and worker heartbeat status. Web requests only queue work.
- Added atomic private artifact writes, per-digest database transactions, resumable
  message identities, PDF/content deduplication, and interrupted-worker recovery.
- Shared importer validation now rejects missing timestamps and invalid fields,
  reports invalid records with a nonzero exit code, and supports `--source` while
  preserving existing stock/timestamp skip behavior. Numeric fields round to model
  precision. Existing local JSON files remain usable.
- Added migration `stocks.0002`, runtime dependencies, private environment example,
  IDE worker configuration, and `docs/INGESTION.md`. Existing CI/hooks discover and
  validate the new tests; no extra workflow rules or helper scripts are required.
- Included the existing local app-review notes, README corrections, and runserver
  configuration edit in the `feature/bofa-ingestion` pull-request scope.

### Verification

- All 47 Django tests passed, including offline pipeline integration, retry/rollback,
  staff permissions/CSRF, legacy duplicate detection, and a separate-connection
  PostgreSQL worker-lock check. Django system checks and migration drift check pass.
- `import_reports --dry-run` validated all 17,307 local source records without writes.
- Applied `stocks.0002` to the local database. A live one-message dry-run authenticated
  to Gmail, downloaded the PDF, and extracted/validated all 21 company reports.
- A live real sync recognized all 21 as existing content, creating zero duplicate
  reports. A repeat sync skipped the completed message without refetching it. The
  database retained 17,307 reports. A local worker was started at a 900-second interval
  and its heartbeat was observed. This process is not installed as an OS service.
- All applicable configured hooks passed on changed files; YAML checking skipped
  because no YAML files changed. The pre-existing runserver edit was excluded from
  task hook inputs. `git diff --check` passed.
- Release preparation also passed the complete `prek run --all-files` suite,
  including YAML checks, with the app-review documentation and runserver changes
  included. Both IDE run configurations parsed successfully as XML. The 47 tests,
  Django checks, and migration drift check passed again before publication.
- Live integration initially exposed unquoted dotenv password handling, legacy HTTP
  BofA entry links, and indirect PDF annotation arrays. Those paths were corrected
  and the live sync rerun successfully. Migration drift from tuple/list ordering
  metadata was corrected without introducing another migration.
- Sandbox-denied uv/prek tool caches were redirected to temporary writable paths.
  Runtime secrets and downloaded artifacts remain Git-ignored and private. No
  credentials, report URLs, or downloaded source content were committed.

### Remaining Operational Boundaries

- Keep the worker and Gmail forwarding active; use a process manager to restart the
  worker after logout/reboot in a persistent environment. This task did not install
  system services or validate production deployment or backup restoration.
- Live verification covered the latest digest, not every historical publication.
  Inline forwarding can lose original dates, and unavailable company publications
  remain explicit retryable failures. Artifacts currently require manual retention.

## Twice-Daily Report Schedule: November 11, 2026

- Changed automatic syncs from a 900-second interval to 11:00 and 17:00 daily in
  America/New_York, with automatic daylight saving handling. Staff requests remain
  immediate; the worker stays available between scheduled report downloads.
- Added environment/CLI settings for daily times and timezone. The explicit
  `--interval` development override remains; the former `BOFA_SYNC_INTERVAL`
  environment setting is replaced by `BOFA_SYNC_TIMES` / `BOFA_SYNC_TIMEZONE`.
- Restarts catch up only today's latest elapsed slot. A full sync queued after a
  slot suppresses repeat scheduling, including after failure. Dry-runs and limited
  spot checks do not consume daily slots. Manual sync retries remain available.
- Added boundary, restart/deduplication, manual-queue, invalid-configuration, and
  daylight saving transition coverage. No database migration, CI, hook, IDE run
  configuration, or helper-script changes are needed for this scheduling change.
- All 51 tests passed; Django system and migration drift checks passed. Replaced
  the local interval worker with the daily schedule. The first scheduling test
  required aligning Django's captured field-default timestamp with its mocked clock.
