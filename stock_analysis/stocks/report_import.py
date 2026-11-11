"""Shared validation and persistence for file imports and unattended ingestion."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.db import transaction
from django.utils import timezone

from stocks.models import DailyReport, EPSForecast, ReportKeyTakeaway, Stock

TS_FORMAT = "%Y-%m-%d_%H-%M"
EPS_YEAR_RE = re.compile(r"^(?P<year>20\d{2})(?:E)?_EPS$")
EPS_CODE_RE = re.compile(r"^(?P<code>\d{3})_EPS$")


def to_decimal(value):
    if value in ("", None):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid numeric value") from error
    if not result.is_finite():
        raise ValueError("Numeric values must be finite")
    return result


def extract_eps_year(key):
    match = EPS_YEAR_RE.match(key)
    if match:
        return int(match.group("year"))
    match = EPS_CODE_RE.match(key)
    return int(match.group("code")) + 1700 if match else None


def eps_priority(key):
    if EPS_YEAR_RE.match(key):
        return 3 if "E_" in key else 2
    return 1 if EPS_CODE_RE.match(key) else 0


def parse_ticker_region(value):
    parts = value.split() if isinstance(value, str) else []
    if len(parts) != 2:
        raise ValueError("Ticker must contain ticker and region, e.g. 'COP US'")
    return parts[0].upper(), parts[1].upper()


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError(
            "Timestamp is required; refusing to substitute the current time"
        )
    return timezone.make_aware(
        datetime.strptime(value, TS_FORMAT), timezone.get_current_timezone()
    )


def canonical_link(value):
    parts = urlsplit(value)
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in {"ps", "pv"}
    )
    path = "/access" if parts.path == "/r" else parts.path
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def fingerprint(ticker, region, fields, takeaways, eps):
    values = dict(fields)
    values["link"] = canonical_link(values["link"])
    payload = [ticker, region, values, takeaways, sorted(eps)]

    def encode(value):
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        raise TypeError(f"Unsupported fingerprint value: {type(value).__name__}")

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=encode, ensure_ascii=True).encode()
    ).hexdigest()


@dataclass
class PreparedReport:
    ticker: str
    region: str
    company: str
    currency: str
    timestamp: datetime
    fields: dict
    takeaways: list
    eps: list
    fingerprint: str


def prepare_record(item):
    if not isinstance(item, dict):
        raise TypeError("Each report must be a JSON object")
    ticker, region = parse_ticker_region(item.get("Ticker"))
    timestamp = parse_timestamp(item.get("Timestamp"))
    stock = Stock(
        ticker=ticker,
        region=region,
        company_name=item.get("Company") or "",
        currency_code=(item.get("Currency") or "USD").strip().upper(),
    )
    stock.full_clean(validate_unique=False, validate_constraints=False)
    fields = {
        name: item.get(key) or ""
        for name, key in {
            "link": "Link",
            "blurb": "Blurb",
            "rating": "Rating",
            "analyst_team": "Analyst_Team",
            "report_subtitle": "Report_Subtitle",
        }.items()
    }
    fields["rating"] = DailyReport._meta.get_field("rating").normalize(fields["rating"])
    fields["raw_text"] = item.get("Raw_Text") or []
    takeaways = item.get("Key_Takeaways") or []
    for values in (fields["raw_text"], takeaways):
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError("Raw_Text and Key_Takeaways must be arrays of strings")
    takeaways = [value for value in takeaways if value]
    for name, key in {
        "price": "Price",
        "price_objective": "Price_Objective",
        "upside": "Upside",
        "average_daily_value": "Average_Daily_Value",
        "market_cap": "Market_Cap",
    }.items():
        value = to_decimal(item.get(key))
        if value is not None:
            try:
                value = value.quantize(
                    Decimal(1).scaleb(-DailyReport._meta.get_field(name).decimal_places)
                )
            except InvalidOperation as error:
                raise ValueError(
                    f"{key} is outside the supported numeric range"
                ) from error
        fields[name] = value
    report = DailyReport(as_of_timestamp=timestamp, **fields)
    report.full_clean(
        exclude=["stock"], validate_unique=False, validate_constraints=False
    )
    eps_values = {}
    for key, value in item.items():
        year = extract_eps_year(key)
        if year is not None and value not in (None, ""):
            priority = eps_priority(key)
            if year not in eps_values or priority > eps_values[year][0]:
                try:
                    number = to_decimal(value).quantize(Decimal("0.000001"))
                except InvalidOperation as error:
                    raise ValueError(
                        "EPS is outside the supported numeric range"
                    ) from error
                EPSForecast(year=year, eps=number).full_clean(
                    exclude=["report"],
                    validate_unique=False,
                    validate_constraints=False,
                )
                eps_values[year] = (priority, number)
    eps = sorted((year, entry[1]) for year, entry in eps_values.items())
    return PreparedReport(
        ticker,
        region,
        stock.company_name,
        stock.currency_code,
        timestamp,
        fields,
        takeaways,
        eps,
        fingerprint(ticker, region, fields, takeaways, eps),
    )


def legacy_duplicate(prepared):
    # Older manual imports have no fingerprint. Compare content and child rows
    # so forwarding an old digest cannot invent a new report timestamp.
    candidates = DailyReport.objects.filter(
        stock__ticker=prepared.ticker,
        stock__region=prepared.region,
        ingestion_fingerprint="",
    ).prefetch_related("key_takeaways", "eps_forecasts")
    for report in candidates:
        fields = {key: getattr(report, key) for key in prepared.fields}
        takeaways = [row.text for row in report.key_takeaways.all()]
        eps = [(row.year, row.eps) for row in report.eps_forecasts.all()]
        if (
            fingerprint(prepared.ticker, prepared.region, fields, takeaways, eps)
            == prepared.fingerprint
        ):
            return True
    return False


@transaction.atomic
def import_record(prepared, *, deduplicate_content=False):
    if deduplicate_content and (
        DailyReport.objects.filter(ingestion_fingerprint=prepared.fingerprint).exists()
        or legacy_duplicate(prepared)
    ):
        return False
    stock, _ = Stock.objects.get_or_create(
        ticker=prepared.ticker,
        region=prepared.region,
        defaults={"company_name": prepared.company, "currency_code": prepared.currency},
    )
    report, created = DailyReport.objects.get_or_create(
        stock=stock,
        as_of_timestamp=prepared.timestamp,
        defaults={**prepared.fields, "ingestion_fingerprint": prepared.fingerprint},
    )
    if created:
        ReportKeyTakeaway.objects.bulk_create(
            [
                ReportKeyTakeaway(report=report, order=i, text=value)
                for i, value in enumerate(prepared.takeaways)
            ]
        )
        EPSForecast.objects.bulk_create(
            [
                EPSForecast(report=report, year=year, eps=value)
                for year, value in prepared.eps
            ]
        )
    return created
