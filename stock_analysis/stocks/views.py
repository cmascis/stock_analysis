from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from investor.models import HoldingSnapshot, Watch
from stocks.models import DailyReport, Stock

NUMERIC_FILTER_CONFIG = [
    {
        "key": "price",
        "label": "Price",
        "field": "latest_price",
        "step": Decimal("0.01"),
        "prefix": "$",
    },
    {
        "key": "price_objective",
        "label": "Price Objective",
        "field": "latest_price_objective",
        "step": Decimal("0.01"),
        "prefix": "$",
    },
    {
        "key": "upside_pct",
        "label": "Upside %",
        "field": "latest_upside_pct",
        "step": Decimal("0.10"),
        "suffix": "%",
    },
    {
        "key": "market_cap",
        "label": "Market Cap",
        "field": "latest_market_cap",
        "step": Decimal("1000000"),
        "prefix": "$",
    },
    {
        "key": "average_daily_value",
        "label": "Average Daily Value",
        "field": "latest_average_daily_value",
        "step": Decimal("1000000"),
        "prefix": "$",
    },
]

SORT_FIELD_CHOICES = [
    ("latest_report_at", "Most Recent Report Date"),
    ("upside", "Upside %"),
    ("price_objective", "Price Objective"),
    ("price", "Price"),
    ("market_cap", "Market Cap"),
    ("average_daily_value", "Average Daily Value"),
    ("rating", "Rating"),
    ("analyst_team", "Analyst Team"),
    ("ticker", "Ticker"),
    ("company_name", "Company Name"),
    ("region", "Region"),
    ("currency_code", "Currency"),
]

SORT_FIELD_MAP = {
    "latest_report_at": "latest_report_at",
    "upside": "latest_upside",
    "price_objective": "latest_price_objective",
    "price": "latest_price",
    "market_cap": "latest_market_cap",
    "average_daily_value": "latest_average_daily_value",
    "rating": "latest_rating",
    "analyst_team": "latest_analyst_team",
    "ticker": "ticker",
    "company_name": "company_name",
    "region": "region",
    "currency_code": "currency_code",
}

DEFAULT_SORT_PRIORITY = [
    ("latest_report_at", "desc"),
    ("upside", "desc"),
]


def _to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_to_str(value):
    if value is None:
        return ""
    return format(value, "f")


def _decimal_pretty(value):
    if value is None:
        return "-"
    normalized = value.quantize(Decimal("0.01")) if value == value.to_integral_value() else value
    return f"{normalized:,.2f}".rstrip("0").rstrip(".")


def _build_advanced_stock_queryset():
    latest_report = DailyReport.objects.filter(stock=OuterRef("pk")).order_by("-as_of_timestamp")
    latest_price_report = DailyReport.objects.filter(
        stock=OuterRef("pk"),
        price__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_objective_report = DailyReport.objects.filter(
        stock=OuterRef("pk"),
        price_objective__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_upside_report = DailyReport.objects.filter(
        stock=OuterRef("pk"),
        upside__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_market_cap_report = DailyReport.objects.filter(
        stock=OuterRef("pk"),
        market_cap__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_adv_report = DailyReport.objects.filter(
        stock=OuterRef("pk"),
        average_daily_value__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_rating_report = DailyReport.objects.filter(stock=OuterRef("pk")).exclude(rating="").order_by("-as_of_timestamp")
    latest_team_report = DailyReport.objects.filter(stock=OuterRef("pk")).exclude(analyst_team="").order_by(
        "-as_of_timestamp"
    )

    return (
        Stock.objects.annotate(
            latest_report_at=Subquery(latest_report.values("as_of_timestamp")[:1]),
            latest_price=Subquery(latest_price_report.values("price")[:1]),
            latest_price_as_of=Subquery(latest_price_report.values("as_of_timestamp")[:1]),
            latest_price_objective=Subquery(latest_objective_report.values("price_objective")[:1]),
            latest_price_objective_as_of=Subquery(latest_objective_report.values("as_of_timestamp")[:1]),
            latest_upside=Subquery(latest_upside_report.values("upside")[:1]),
            latest_upside_as_of=Subquery(latest_upside_report.values("as_of_timestamp")[:1]),
            latest_market_cap=Subquery(latest_market_cap_report.values("market_cap")[:1]),
            latest_market_cap_as_of=Subquery(latest_market_cap_report.values("as_of_timestamp")[:1]),
            latest_average_daily_value=Subquery(latest_adv_report.values("average_daily_value")[:1]),
            latest_average_daily_value_as_of=Subquery(latest_adv_report.values("as_of_timestamp")[:1]),
            latest_rating=Subquery(latest_rating_report.values("rating")[:1]),
            latest_rating_as_of=Subquery(latest_rating_report.values("as_of_timestamp")[:1]),
            latest_analyst_team=Subquery(latest_team_report.values("analyst_team")[:1]),
            latest_analyst_team_as_of=Subquery(latest_team_report.values("as_of_timestamp")[:1]),
        )
        .annotate(
            latest_upside_pct=ExpressionWrapper(
                F("latest_upside") * Value(Decimal("100")),
                output_field=DecimalField(max_digits=12, decimal_places=4),
            )
        )
        .filter(latest_report_at__isnull=False)
    )


def _get_sort_priority(request_get):
    seen_keys = set()
    priority = []
    for index in range(1, 4):
        field_key = (request_get.get(f"sort{index}_field") or "").strip()
        direction = (request_get.get(f"sort{index}_dir") or "desc").strip().lower()
        if field_key not in SORT_FIELD_MAP or field_key in seen_keys:
            continue
        if direction not in {"asc", "desc"}:
            direction = "desc"
        priority.append((field_key, direction))
        seen_keys.add(field_key)

    if priority:
        return priority
    return list(DEFAULT_SORT_PRIORITY)


def _build_sort_controls(sort_priority):
    controls = []
    for idx in range(3):
        if idx < len(sort_priority):
            field, direction = sort_priority[idx]
        else:
            field, direction = "", "desc"
        controls.append(
            {
                "index": idx + 1,
                "field": field,
                "direction": direction,
            }
        )
    return controls


def _apply_ordering(queryset, sort_priority):
    ordering = []
    for field_key, direction in sort_priority:
        orm_field = SORT_FIELD_MAP[field_key]
        if direction == "desc":
            ordering.append(F(orm_field).desc(nulls_last=True))
        else:
            ordering.append(F(orm_field).asc(nulls_last=True))
    if "ticker" not in [key for key, _ in sort_priority]:
        ordering.append("ticker")
    if "region" not in [key for key, _ in sort_priority]:
        ordering.append("region")
    return queryset.order_by(*ordering)


def _build_priority_labels(sort_priority):
    label_map = dict(SORT_FIELD_CHOICES)
    labels = []
    for field_key, direction in sort_priority:
        labels.append(f"{label_map.get(field_key, field_key)} ({'Descending' if direction == 'desc' else 'Ascending'})")
    return labels

def _to_percent(value):
    if value is None:
        return None
    return value * Decimal("100")


def _build_holdings_rows(user):
    latest_snapshot = HoldingSnapshot.objects.filter(
        user=user,
        stock=OuterRef("pk"),
    ).order_by("-as_of", "-id")

    latest_report = DailyReport.objects.filter(stock=OuterRef("pk")).order_by("-as_of_timestamp")

    holdings = (
        Stock.objects.filter(holding_snapshots__user=user)
        .distinct()
        .annotate(
            holding_quantity=Subquery(latest_snapshot.values("quantity")[:1]),
            holding_avg_cost=Subquery(latest_snapshot.values("avg_cost")[:1]),
            holding_as_of=Subquery(latest_snapshot.values("as_of")[:1]),
            latest_report_at=Subquery(latest_report.values("as_of_timestamp")[:1]),
            latest_price=Subquery(latest_report.values("price")[:1]),
            latest_price_objective=Subquery(latest_report.values("price_objective")[:1]),
            latest_upside=Subquery(latest_report.values("upside")[:1]),
            latest_rating=Subquery(latest_report.values("rating")[:1]),
        )
        .order_by("ticker", "region")
    )

    rows = []
    for stock in holdings:
        quantity = stock.holding_quantity
        price = stock.latest_price
        objective = stock.latest_price_objective
        avg_cost = stock.holding_avg_cost

        position_value = quantity * price if quantity is not None and price is not None else None
        cost_basis_value = quantity * avg_cost if quantity is not None and avg_cost is not None else None
        objective_value = quantity * objective if quantity is not None and objective is not None else None
        target_change_value = (
            quantity * (objective - price)
            if quantity is not None and objective is not None and price is not None
            else None
        )

        rows.append(
            {
                "stock": stock,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "holding_as_of": stock.holding_as_of,
                "report_at": stock.latest_report_at,
                "price": price,
                "price_objective": objective,
                "upside_pct": _to_percent(stock.latest_upside),
                "rating": stock.latest_rating,
                "position_value": position_value,
                "cost_basis_value": cost_basis_value,
                "objective_value": objective_value,
                "target_change_value": target_change_value,
            }
        )
    return rows


def _build_watchlist_rows(user):
    latest_report = DailyReport.objects.filter(stock=OuterRef("stock_id")).order_by("-as_of_timestamp")

    watches = (
        Watch.objects.filter(user=user)
        .select_related("stock")
        .annotate(
            latest_report_at=Subquery(latest_report.values("as_of_timestamp")[:1]),
            latest_rating=Subquery(latest_report.values("rating")[:1]),
            latest_price=Subquery(latest_report.values("price")[:1]),
            latest_price_objective=Subquery(latest_report.values("price_objective")[:1]),
            latest_upside=Subquery(latest_report.values("upside")[:1]),
            latest_analyst_team=Subquery(latest_report.values("analyst_team")[:1]),
        )
        .order_by("-latest_report_at", "stock__ticker")
    )

    rows = []
    for watch in watches:
        rows.append(
            {
                "stock": watch.stock,
                "report_at": watch.latest_report_at,
                "rating": watch.latest_rating,
                "price": watch.latest_price,
                "price_objective": watch.latest_price_objective,
                "upside_pct": _to_percent(watch.latest_upside),
                "analyst_team": watch.latest_analyst_team,
            }
        )
    return rows


def _build_window_summary(window_label, start_at):
    reports = DailyReport.objects.filter(as_of_timestamp__gte=start_at)
    report_count = reports.count()

    best_upside_report = (
        reports.filter(upside__isnull=False)
        .select_related("stock")
        .order_by("-upside", "-as_of_timestamp")
        .first()
    )

    most_reported = (
        reports.values(
            "stock_id",
            "stock__ticker",
            "stock__region",
            "stock__company_name",
        )
        .annotate(report_count=Count("id"))
        .order_by("-report_count", "stock__ticker")
        .first()
    )

    latest_per_stock = reports.order_by("stock_id", "-as_of_timestamp").distinct("stock_id")
    previous_price_objective = Subquery(
        DailyReport.objects.filter(
            stock=OuterRef("stock_id"),
            as_of_timestamp__lt=OuterRef("as_of_timestamp"),
            price_objective__isnull=False,
        )
        .order_by("-as_of_timestamp")
        .values("price_objective")[:1]
    )

    upgrade_candidates = (
        latest_per_stock.annotate(
            previous_price_objective=previous_price_objective,
            objective_upgrade=ExpressionWrapper(
                F("price_objective") - F("previous_price_objective"),
                output_field=DecimalField(max_digits=20, decimal_places=6),
            ),
        )
        .filter(
            price_objective__isnull=False,
            previous_price_objective__isnull=False,
            objective_upgrade__gt=0,
        )
        .select_related("stock")
    )
    largest_upgrade_report = max(
        upgrade_candidates,
        key=lambda report: (report.objective_upgrade, report.as_of_timestamp),
        default=None,
    )

    return {
        "label": window_label,
        "report_count": report_count,
        "best_upside": (
            {
                "stock": best_upside_report.stock,
                "company_name": best_upside_report.stock.company_name,
                "upside_pct": _to_percent(best_upside_report.upside),
                "as_of": best_upside_report.as_of_timestamp,
            }
            if best_upside_report
            else None
        ),
        "most_reported": (
            {
                "stock_id": most_reported["stock_id"],
                "ticker": most_reported["stock__ticker"],
                "region": most_reported["stock__region"],
                "company_name": most_reported["stock__company_name"],
                "report_count": most_reported["report_count"],
            }
            if most_reported
            else None
        ),
        "largest_upgrade": (
            {
                "stock": largest_upgrade_report.stock,
                "company_name": largest_upgrade_report.stock.company_name,
                "from_objective": largest_upgrade_report.previous_price_objective,
                "to_objective": largest_upgrade_report.price_objective,
                "upgrade_amount": largest_upgrade_report.objective_upgrade,
                "as_of": largest_upgrade_report.as_of_timestamp,
            }
            if largest_upgrade_report
            else None
        ),
    }


def _build_report_windows_summary():
    now = timezone.now()
    return [
        _build_window_summary("Last 24 Hours", now - timedelta(days=1)),
        _build_window_summary("Last 7 Days", now - timedelta(days=7)),
        _build_window_summary("Last 30 Days", now - timedelta(days=30)),
    ]


def home(request):
    context = {}
    if request.user.is_authenticated:
        holdings_rows = _build_holdings_rows(request.user)
        watchlist_rows = _build_watchlist_rows(request.user)

        total_position_value = sum((row["position_value"] or Decimal("0")) for row in holdings_rows)
        total_target_change = sum((row["target_change_value"] or Decimal("0")) for row in holdings_rows)

        context.update(
            {
                "holdings_rows": holdings_rows,
                "watchlist_rows": watchlist_rows,
                "report_windows": _build_report_windows_summary(),
                "holdings_count": len(holdings_rows),
                "watchlist_count": len(watchlist_rows),
                "total_position_value": total_position_value,
                "total_target_change": total_target_change,
            }
        )

    return render(request, "stocks/home.html", context)


def stock_search_suggestions(request):
    query = (request.GET.get("q") or "").strip()
    if not query:
        return JsonResponse({"results": []})

    results = (
        Stock.objects.filter(Q(ticker__icontains=query) | Q(company_name__icontains=query))
        .annotate(
            match_priority=Case(
                When(ticker__iexact=query, then=Value(0)),
                When(ticker__istartswith=query, then=Value(1)),
                When(company_name__istartswith=query, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by("match_priority", "ticker", "region")[:8]
    )

    payload = [
        {
            "id": stock.id,
            "ticker": stock.ticker,
            "region": stock.region,
            "company_name": stock.company_name,
            "url": reverse("stock_detail", args=[stock.id]),
        }
        for stock in results
    ]
    return JsonResponse({"results": payload})


def advanced_stock_search(request):
    queryset = _build_advanced_stock_queryset()
    active_filters = []

    search_text = (request.GET.get("q") or "").strip()
    ticker_filter = (request.GET.get("ticker") or "").strip()
    company_filter = (request.GET.get("company_name") or "").strip()
    region_filter = (request.GET.get("region") or "").strip()
    currency_filter = (request.GET.get("currency_code") or "").strip()

    if search_text:
        queryset = queryset.filter(Q(ticker__icontains=search_text) | Q(company_name__icontains=search_text))
        active_filters.append(f"Name contains '{search_text}'")
    if ticker_filter:
        queryset = queryset.filter(ticker__icontains=ticker_filter)
        active_filters.append(f"Ticker contains '{ticker_filter.upper()}'")
    if company_filter:
        queryset = queryset.filter(company_name__icontains=company_filter)
        active_filters.append(f"Company contains '{company_filter}'")
    if region_filter:
        queryset = queryset.filter(region__icontains=region_filter)
        active_filters.append(f"Region contains '{region_filter.upper()}'")
    if currency_filter:
        queryset = queryset.filter(currency_code__icontains=currency_filter)
        active_filters.append(f"Currency contains '{currency_filter.upper()}'")

    bounds = queryset.aggregate(
        price_min_bound=Min("latest_price"),
        price_max_bound=Max("latest_price"),
        price_objective_min_bound=Min("latest_price_objective"),
        price_objective_max_bound=Max("latest_price_objective"),
        upside_pct_min_bound=Min("latest_upside_pct"),
        upside_pct_max_bound=Max("latest_upside_pct"),
        market_cap_min_bound=Min("latest_market_cap"),
        market_cap_max_bound=Max("latest_market_cap"),
        average_daily_value_min_bound=Min("latest_average_daily_value"),
        average_daily_value_max_bound=Max("latest_average_daily_value"),
    )

    numeric_filter_controls = []
    for config in NUMERIC_FILTER_CONFIG:
        key = config["key"]
        field_name = config["field"]
        min_key = f"{key}_min"
        max_key = f"{key}_max"
        raw_min_value = (request.GET.get(min_key) or "").strip()
        raw_max_value = (request.GET.get(max_key) or "").strip()
        min_value = _to_decimal(raw_min_value)
        max_value = _to_decimal(raw_max_value)

        if min_value is not None and max_value is not None and min_value > max_value:
            min_value, max_value = max_value, min_value

        if min_value is not None:
            queryset = queryset.filter(**{f"{field_name}__gte": min_value})
        if max_value is not None:
            queryset = queryset.filter(**{f"{field_name}__lte": max_value})

        if min_value is not None or max_value is not None:
            if min_value is not None and max_value is not None:
                active_filters.append(
                    f"{config['label']} between {config.get('prefix', '')}{_decimal_pretty(min_value)}"
                    f"{config.get('suffix', '')} and {config.get('prefix', '')}{_decimal_pretty(max_value)}"
                    f"{config.get('suffix', '')}"
                )
            elif min_value is not None:
                active_filters.append(
                    f"{config['label']} >= {config.get('prefix', '')}{_decimal_pretty(min_value)}{config.get('suffix', '')}"
                )
            else:
                active_filters.append(
                    f"{config['label']} <= {config.get('prefix', '')}{_decimal_pretty(max_value)}{config.get('suffix', '')}"
                )

        bound_min = bounds.get(f"{key}_min_bound")
        bound_max = bounds.get(f"{key}_max_bound")
        slider_min = bound_min if bound_min is not None else Decimal("0")
        slider_max = bound_max if bound_max is not None else Decimal("0")
        if slider_max < slider_min:
            slider_min, slider_max = slider_max, slider_min
        range_min_value = min_value if min_value is not None else slider_min
        range_max_value = max_value if max_value is not None else slider_max

        numeric_filter_controls.append(
            {
                "key": key,
                "label": config["label"],
                "prefix": config.get("prefix", ""),
                "suffix": config.get("suffix", ""),
                "min_param": min_key,
                "max_param": max_key,
                "step": _decimal_to_str(config["step"]),
                "bound_min": _decimal_to_str(slider_min),
                "bound_max": _decimal_to_str(slider_max),
                "bound_min_display": _decimal_pretty(slider_min),
                "bound_max_display": _decimal_pretty(slider_max),
                "range_min": _decimal_to_str(range_min_value),
                "range_max": _decimal_to_str(range_max_value),
                "input_min": _decimal_to_str(min_value) if min_value is not None else "",
                "input_max": _decimal_to_str(max_value) if max_value is not None else "",
            }
        )

    sort_priority = _get_sort_priority(request.GET)
    queryset = _apply_ordering(queryset, sort_priority)

    paginator = Paginator(queryset, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_window_start = max(page_obj.number - 2, 1)
    page_window_end = min(page_obj.number + 2, paginator.num_pages)
    page_numbers = range(page_window_start, page_window_end + 1)

    query_params = request.GET.copy()
    query_params.pop("page", None)
    querystring_without_page = query_params.urlencode()

    sort_priority_labels = _build_priority_labels(sort_priority)
    if active_filters and sort_priority_labels:
        query_statement = f"{'; '.join(active_filters)}; ordered by {' -> '.join(sort_priority_labels)}"
    elif active_filters:
        query_statement = "; ".join(active_filters)
    elif sort_priority_labels:
        query_statement = f"Ordered by {' -> '.join(sort_priority_labels)}"
    else:
        query_statement = ""

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "page_numbers": page_numbers,
        "sort_field_choices": SORT_FIELD_CHOICES,
        "sort_controls": _build_sort_controls(sort_priority),
        "numeric_filter_controls": numeric_filter_controls,
        "active_filters": active_filters,
        "sort_priority_labels": sort_priority_labels,
        "query_statement": query_statement,
        "querystring_without_page": querystring_without_page,
    }
    return render(request, "stocks/advanced_search.html", context)


def stock_detail(request, stock_id):
    stock = get_object_or_404(Stock, pk=stock_id)
    reports = list(
        DailyReport.objects.filter(stock=stock)
        .prefetch_related("key_takeaways", "eps_forecasts")
        .order_by("-as_of_timestamp")
    )

    chart_reports = [
        report
        for report in reversed(reports)
        if report.price is not None or report.price_objective is not None
    ]
    chart_labels = [report.as_of_timestamp.strftime("%Y-%m-%d") for report in chart_reports]
    chart_price_values = [float(report.price) if report.price is not None else None for report in chart_reports]
    chart_objective_values = [
        float(report.price_objective) if report.price_objective is not None else None
        for report in chart_reports
    ]
    chart_has_data = any(
        value is not None
        for value in (chart_price_values + chart_objective_values)
    )

    latest_report = reports[0] if reports else None
    previous_report = reports[1] if len(reports) > 1 else None
    objective_change = None
    if (
        latest_report
        and previous_report
        and latest_report.price_objective is not None
        and previous_report.price_objective is not None
    ):
        objective_change = latest_report.price_objective - previous_report.price_objective

    context = {
        "stock": stock,
        "reports": reports,
        "report_count": len(reports),
        "latest_report": latest_report,
        "latest_upside_pct": _to_percent(latest_report.upside) if latest_report else None,
        "objective_change": objective_change,
        "chart_labels": chart_labels,
        "chart_price_values": chart_price_values,
        "chart_objective_values": chart_objective_values,
        "chart_has_data": chart_has_data,
    }
    return render(request, "stocks/stock_detail.html", context)
