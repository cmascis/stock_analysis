# Architecture

## Application Shape

- Framework: Django, server-rendered templates.
- Architecture style: single-project monolith, function-view-heavy, with most business logic in `stocks/views.py`.
- No active REST API namespace or separate service layer in the current implementation.
- Apps:
  - `stocks`: stock universe, analyst reports, advanced search, dashboards, stock detail page.
  - `investor`: profile lifecycle, watchlist, holding snapshots, signup workflow.
- Root routing:
  - `/admin/` -> Django admin
  - `/accounts/` -> Django auth URLs
  - `/accounts/signup/` -> custom signup
  - `/` and stock routes -> `stocks.urls`
- Supporting runtime surfaces:
  - Django admin for data inspection and editing
  - `import_reports` management command for batch report ingestion
  - `post_save` signal that auto-creates `InvestorProfile`

## Data Model

### `stocks` app

- `Stock`
  - identity: `(ticker, region)` unique
  - normalized uppercase ticker/region/currency
- `DailyReport`
  - belongs to one stock
  - unique `(stock, as_of_timestamp)`
  - core numeric fields: `price`, `price_objective`, `upside`, `market_cap`, `average_daily_value`
  - qualitative fields: `rating`, `analyst_team`, `blurb`, `report_subtitle`, `raw_text`
- `ReportKeyTakeaway`
  - ordered takeaways per report
  - unique `(report, order)`
- `EPSForecast`
  - year/eps rows per report
  - unique `(report, year)`

### `investor` app

- `InvestorProfile`
  - one-to-one with user
  - auto-created on user creation signal
- `Watch`
  - unique watchlist edge `(user, stock)`
- `HoldingSnapshot`
  - append-only position snapshots over time
  - unique `(user, stock, as_of)`

## Main Request Flows

### Home (`home`)

- Anonymous:
  - marketing + CTA.
- Authenticated:
  - `holdings_rows`: latest holding snapshot and latest report context per stock.
  - `watchlist_rows`: latest report context for watched stocks.
  - `report_windows`: 24h / 7d / 30d summary cards.
- Heavy lifting:
  - `Subquery`, `OuterRef`, aggregate + derived Decimal calculations.

### Signup (`signup`)

- Uses a custom `InvestorSignupForm`.
- Requires `username`, `email`, `first_name`, `last_name`, `password1`, and `password2`.
- Logs the user in after creation and redirects to `home`.
- `InvestorProfile` is then ensured by the `post_save` signal on the user model.

### Search (`stock_search_suggestions`)

- JSON endpoint powering header search popover.
- Query strategy:
  - ticker/company `icontains`
  - ranked with `Case/When` for exact/startswith behavior.
- Returns up to 8 suggestions with direct stock detail URLs.

### Advanced Search (`advanced_stock_search`)

- Builds per-stock "latest metric" view using annotated subqueries.
- Supports:
  - text filters (`q`, `ticker`, `company_name`, `region`, `currency_code`)
  - numeric min/max filters for price, objective, upside %, market cap, average daily value
  - up to 3-level sort priority
- Result set:
  - paginated 50/page
  - stable tie-break ordering via ticker and region.

### Stock Detail (`stock_detail`)

- Loads full report timeline for one stock.
- Prefetches `key_takeaways` and `eps_forecasts`.
- Builds chart arrays (price/objective over time) in view, rendered with Chart.js in template.
- Provides report carousel controls (newer/older/jump-to-date) client-side.

## Import Pipeline

- Command: `import_reports`
- Input directory: `stock_analysis/company_jsons/*.json`
- Behavior:
  - parse list payloads
  - parse ticker/region from `"Ticker"` value (example `"COP US"`)
  - parse timestamp format `%Y-%m-%d_%H-%M`
  - map numeric/string fields into `DailyReport`
  - derive EPS year from multiple key formats with precedence
  - create stock if missing
  - create report if not existing, then create takeaways and EPS rows
  - skip duplicate report timestamps for same stock
  - skip malformed records with stderr output rather than aborting the whole import

## Frontend Layer

- Base template (`stocks/templates/base.html`) includes:
  - global shell
  - auth nav
  - live stock search UI script
- There is no frontend build step; JavaScript is inline in templates and CSS lives in `stocks/static/stocks/theme.css`.
- Feature templates:
  - `stocks/home.html`
  - `stocks/advanced_search.html`
  - `stocks/stock_detail.html`
  - auth templates in `investor/templates/registration/`
- Styling:
  - centralized in `stocks/static/stocks/theme.css`

## Testing Surface

- `stocks/tests.py`
  - home dashboard context
  - stock detail rendering
  - search endpoint behavior
  - advanced search ordering/filtering behavior
- `investor/tests.py`
  - signup required fields
  - login/logout flow

## Deployment/Runtime Assumptions

- Database backend is PostgreSQL in all environments from current settings.
- DB host/credentials are environment-driven with local defaults:
  - DB name/user/password default to `stock_analysis`
  - host default `localhost`, port `5432`
- Docker Compose provides local Postgres container only.
- `djangorestframework` is installed as a dependency, but no active DRF endpoints or serializers are wired into runtime URLs.
