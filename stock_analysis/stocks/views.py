from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
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


def _to_percent(value):
    if value is None:
        return None
    return value * Decimal("100")


def _build_holdings_rows(user):
    latest_snapshot = HoldingSnapshot.objects.filter(
        user=user,
        stock=OuterRef("pk"),
    ).order_by("-as_of", "-id")

    latest_report = DailyReport.objects.filter(stock=OuterRef("pk")).order_by(
        "-as_of_timestamp"
    )
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
    latest_rating_report = (
        DailyReport.objects.filter(stock=OuterRef("pk"))
        .exclude(rating="")
        .order_by("-as_of_timestamp")
    )

    holdings = (
        Stock.objects.filter(holding_snapshots__user=user)
        .distinct()
        .annotate(
            holding_quantity=Subquery(latest_snapshot.values("quantity")[:1]),
            holding_avg_cost=Subquery(latest_snapshot.values("avg_cost")[:1]),
            holding_as_of=Subquery(latest_snapshot.values("as_of")[:1]),
            latest_report_at=Subquery(latest_report.values("as_of_timestamp")[:1]),
            latest_price=Subquery(latest_price_report.values("price")[:1]),
            latest_price_as_of=Subquery(
                latest_price_report.values("as_of_timestamp")[:1]
            ),
            latest_price_objective=Subquery(
                latest_objective_report.values("price_objective")[:1]
            ),
            latest_price_objective_as_of=Subquery(
                latest_objective_report.values("as_of_timestamp")[:1]
            ),
            latest_upside=Subquery(latest_upside_report.values("upside")[:1]),
            latest_upside_as_of=Subquery(
                latest_upside_report.values("as_of_timestamp")[:1]
            ),
            latest_rating=Subquery(latest_rating_report.values("rating")[:1]),
            latest_rating_as_of=Subquery(
                latest_rating_report.values("as_of_timestamp")[:1]
            ),
        )
        .order_by("ticker", "region")
    )

    rows = []
    for stock in holdings:
        quantity = stock.holding_quantity
        price = stock.latest_price
        objective = stock.latest_price_objective
        avg_cost = stock.holding_avg_cost

        position_value = (
            quantity * price if quantity is not None and price is not None else None
        )
        cost_basis_value = (
            quantity * avg_cost
            if quantity is not None and avg_cost is not None
            else None
        )
        objective_value = (
            quantity * objective
            if quantity is not None and objective is not None
            else None
        )
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
                "price_as_of": stock.latest_price_as_of,
                "price_objective": objective,
                "price_objective_as_of": stock.latest_price_objective_as_of,
                "upside_pct": _to_percent(stock.latest_upside),
                "upside_as_of": stock.latest_upside_as_of,
                "rating": stock.latest_rating,
                "rating_as_of": stock.latest_rating_as_of,
                "position_value": position_value,
                "cost_basis_value": cost_basis_value,
                "objective_value": objective_value,
                "target_change_value": target_change_value,
            }
        )
    return rows


def _build_watchlist_rows(user):
    latest_report = DailyReport.objects.filter(stock=OuterRef("stock_id")).order_by(
        "-as_of_timestamp"
    )
    latest_price_report = DailyReport.objects.filter(
        stock=OuterRef("stock_id"),
        price__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_objective_report = DailyReport.objects.filter(
        stock=OuterRef("stock_id"),
        price_objective__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_upside_report = DailyReport.objects.filter(
        stock=OuterRef("stock_id"),
        upside__isnull=False,
    ).order_by("-as_of_timestamp")
    latest_rating_report = (
        DailyReport.objects.filter(stock=OuterRef("stock_id"))
        .exclude(rating="")
        .order_by("-as_of_timestamp")
    )

    watches = (
        Watch.objects.filter(user=user)
        .select_related("stock")
        .annotate(
            latest_report_at=Subquery(latest_report.values("as_of_timestamp")[:1]),
            latest_rating=Subquery(latest_rating_report.values("rating")[:1]),
            latest_rating_as_of=Subquery(
                latest_rating_report.values("as_of_timestamp")[:1]
            ),
            latest_price=Subquery(latest_price_report.values("price")[:1]),
            latest_price_as_of=Subquery(
                latest_price_report.values("as_of_timestamp")[:1]
            ),
            latest_price_objective=Subquery(
                latest_objective_report.values("price_objective")[:1]
            ),
            latest_price_objective_as_of=Subquery(
                latest_objective_report.values("as_of_timestamp")[:1]
            ),
            latest_upside=Subquery(latest_upside_report.values("upside")[:1]),
            latest_upside_as_of=Subquery(
                latest_upside_report.values("as_of_timestamp")[:1]
            ),
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
                "rating_as_of": watch.latest_rating_as_of,
                "price": watch.latest_price,
                "price_as_of": watch.latest_price_as_of,
                "price_objective": watch.latest_price_objective,
                "price_objective_as_of": watch.latest_price_objective_as_of,
                "upside_pct": _to_percent(watch.latest_upside),
                "upside_as_of": watch.latest_upside_as_of,
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

    latest_per_stock = reports.order_by("stock_id", "-as_of_timestamp").distinct(
        "stock_id"
    )
    previous_price_objective = Subquery(
        DailyReport.objects.filter(
            stock=OuterRef("stock_id"),
            as_of_timestamp__lt=OuterRef("as_of_timestamp"),
            price_objective__isnull=False,
        )
        .order_by("-as_of_timestamp")
        .values("price_objective")[:1]
    )

    objective_candidates = (
        latest_per_stock.annotate(
            previous_price_objective=previous_price_objective,
            objective_change=ExpressionWrapper(
                F("price_objective") - F("previous_price_objective"),
                output_field=DecimalField(max_digits=20, decimal_places=6),
            ),
        )
        .filter(
            price_objective__isnull=False,
            previous_price_objective__isnull=False,
        )
        .select_related("stock")
    )

    objective_candidates = list(objective_candidates)
    largest_upgrade_report = max(
        (report for report in objective_candidates if report.objective_change > 0),
        key=lambda report: (report.objective_change, report.as_of_timestamp),
        default=None,
    )
    largest_downgrade_report = max(
        (report for report in objective_candidates if report.objective_change < 0),
        key=lambda report: (-report.objective_change, report.as_of_timestamp),
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
                "upgrade_amount": largest_upgrade_report.objective_change,
                "as_of": largest_upgrade_report.as_of_timestamp,
            }
            if largest_upgrade_report
            else None
        ),
        "largest_downgrade": (
            {
                "stock": largest_downgrade_report.stock,
                "company_name": largest_downgrade_report.stock.company_name,
                "from_objective": largest_downgrade_report.previous_price_objective,
                "to_objective": largest_downgrade_report.price_objective,
                "downgrade_amount": largest_downgrade_report.previous_price_objective
                - largest_downgrade_report.price_objective,
                "as_of": largest_downgrade_report.as_of_timestamp,
            }
            if largest_downgrade_report
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

        total_position_value = sum(
            (row["position_value"] or Decimal("0")) for row in holdings_rows
        )
        total_target_change = sum(
            (row["target_change_value"] or Decimal("0")) for row in holdings_rows
        )

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
        Stock.objects.filter(
            Q(ticker__icontains=query) | Q(company_name__icontains=query)
        )
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
    chart_labels = [
        report.as_of_timestamp.strftime("%Y-%m-%d") for report in chart_reports
    ]
    chart_price_values = [
        float(report.price) if report.price is not None else None
        for report in chart_reports
    ]
    chart_objective_values = [
        float(report.price_objective) if report.price_objective is not None else None
        for report in chart_reports
    ]
    chart_has_data = any(
        value is not None for value in (chart_price_values + chart_objective_values)
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
        objective_change = (
            latest_report.price_objective - previous_report.price_objective
        )

    context = {
        "stock": stock,
        "reports": reports,
        "report_count": len(reports),
        "latest_report": latest_report,
        "latest_upside_pct": _to_percent(latest_report.upside)
        if latest_report
        else None,
        "objective_change": objective_change,
        "chart_labels": chart_labels,
        "chart_price_values": chart_price_values,
        "chart_objective_values": chart_objective_values,
        "chart_has_data": chart_has_data,
    }
    return render(request, "stocks/stock_detail.html", context)
