import json
import re
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from stocks.models import Stock, DailyReport, ReportKeyTakeaway, EPSForecast
from django.conf import settings
from decimal import Decimal

json_dir = Path(settings.BASE_DIR) / "company_jsons"

TS_FORMAT = "%Y-%m-%d_%H-%M"  # matches "2026-01-16_13-48"
EPS_YEAR_RE = re.compile(r"^(?P<year>20\d{2})(?:E)?_EPS$")
EPS_CODE_RE = re.compile(r"^(?P<code>\d{3})_EPS$")


def to_decimal(v):
    return None if v in ("", None) else Decimal(str(v))

def extract_eps_year(key: str) -> int | None:
    """
    Returns the year for EPS keys or None if the key isn't an EPS field.

    Supports:
      - 2027E_EPS -> 2027
      - 2027_EPS  -> 2027
      - 327_EPS   -> 2027 (code + 1700)
    """
    m = EPS_YEAR_RE.match(key)
    if m:
        return int(m.group("year"))

    m = EPS_CODE_RE.match(key)
    if m:
        code = int(m.group("code"))
        return code + 1700  # 325->2025, 326->2026, 327->2027

    return None

def eps_priority(key: str) -> int:
    # higher is better
    if re.match(r"^20\d{2}E_EPS$", key):
        return 3
    if re.match(r"^20\d{2}_EPS$", key):
        return 2
    if re.match(r"^\d{3}_EPS$", key):
        return 1
    return 0

def parse_ticker_region(s: str) -> tuple[str, str]:
    """
    "COP US" -> ("COP", "US")
    """
    parts = (s or "").split()
    if len(parts) < 2:
        raise ValueError(f"Bad Ticker format: {s!r} (expected like 'COP US')")
    return parts[0], parts[1]


def parse_timestamp(ts: str):
    if not ts:
        return timezone.now()
    # naive datetime; Django will make it aware if USE_TZ=True when saving
    dt = datetime.strptime(ts, TS_FORMAT)
    return timezone.make_aware(dt, timezone.get_current_timezone())


class Command(BaseCommand):
    help = "Import stock reports from one JSON file or a directory of JSON files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate, but don't write to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        files = sorted(json_dir.glob("*.json"))

        if not files:
            raise CommandError(f"No JSON files found at: {json_dir}")

        self.stdout.write(f"Found {len(files)} file(s). Dry-run={dry_run}")

        total_reports = 0
        created_reports = 0
        skipped_reports = 0

        for fp in files:
            self.stdout.write(f"\nProcessing: {fp}")
            data = json.loads(fp.read_text(encoding="utf-8"))

            if not isinstance(data, list):
                raise CommandError(f"Top-level JSON must be a list in {fp}")

            for item in data:
                total_reports += 1

                ticker_raw = item.get("Ticker", "")
                try:
                    ticker, region = parse_ticker_region(ticker_raw)
                    as_of_ts = parse_timestamp(item.get("Timestamp"))
                except Exception as e:
                    self.stderr.write(f"Skipping bad record in {fp}: {e}")
                    continue

                currency = item.get("Currency", "USD") or "USD"
                company_name = item.get("Company", "") or ""

                # Build report fields (map JSON keys -> model fields)
                report_defaults = {
                    "link": item.get("Link", "") or "",
                    "blurb": item.get("Blurb", "") or "",
                    "rating": item.get("Rating", "") or "",
                    "analyst_team": item.get("Analyst_Team", "") or "",
                    "report_subtitle": item.get("Report_Subtitle", "") or "",
                    "raw_text": item.get("Raw_Text", []) or [],
                    "price": to_decimal(item.get("Price", None)),
                    "price_objective": to_decimal(item.get("Price_Objective", None)),
                    "upside": to_decimal(item.get("Upside", None)),
                    "average_daily_value": to_decimal(item.get("Average_Daily_Value", None)),
                    "market_cap": to_decimal(item.get("Market_Cap", None)),
                }

                key_takeaways = item.get("Key_Takeaways", []) or []

                eps_by_year = {}
                eps_source_pri = {}

                for k, v in item.items():
                    year = extract_eps_year(k)
                    if year is None or v in ("", None):
                        continue

                    pri = eps_priority(k)
                    if (year not in eps_by_year) or (pri > eps_source_pri[year]):
                        eps_val = to_decimal(v)
                        if eps_val is None:
                            continue
                        eps_by_year[year] = eps_val
                        eps_source_pri[year] = pri

                eps_rows = sorted(eps_by_year.items())  # [(2025, ...), (2026, ...)]

                if dry_run:
                    continue

                with transaction.atomic():
                    stock, _created = Stock.objects.get_or_create(
                        ticker=ticker,
                        region=region,
                        defaults={
                            "company_name": company_name,
                            "currency_code": currency,
                        },
                    )

                    # Upsert DailyReport using your uniqueness constraint
                    report, report_created = DailyReport.objects.get_or_create(
                        stock=stock,
                        as_of_timestamp=as_of_ts,
                        defaults=report_defaults,
                    )

                    if report_created:
                        created_reports += 1

                        # Create takeaways (simple + deterministic)
                        ReportKeyTakeaway.objects.bulk_create(
                            [
                                ReportKeyTakeaway(report=report, order=i, text=text)
                                for i, text in enumerate(key_takeaways)
                                if text
                            ]
                        )

                        # Create EPS (simple + deterministic)
                        EPSForecast.objects.bulk_create(
                            [
                                EPSForecast(report=report, year=year, eps=eps)
                                for (year, eps) in eps_rows
                            ]
                        )
                    else:
                        skipped_reports += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Parsed={total_reports} Created reports={created_reports} Skipped reports={skipped_reports}"
            )
        )
