from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, OuterRef, Subquery
from django.shortcuts import render
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
