from django.shortcuts import render
import json
from datetime import timedelta

from django.db.models import (
    Count,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView

from .models import Stock, DailyReport

# Create your views here.
# stocks/views.py

class HomeView(TemplateView):
    template_name = "stocks/home.html"

    # tweak these as you like
    TOP_N_UPSIDE = 10
    TOP_N_MOST_REPORTED = 10
    CHART_STOCKS_COUNT = 5  # how many of "most reported" get charts
    CHART_MAX_POINTS = 60   # cap points to avoid huge pages

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        now = timezone.now()
        start_7d = now - timedelta(days=7)
        start_30d = now - timedelta(days=30)
        start_365d = now - timedelta(days=365)

        # -------------
        # 1) Top upside stocks (7d / 30d)
        # Interpretation: within the window, take the MAX upside per stock and rank by it.
        # -------------
        top_upside_7d = (
            Stock.objects.annotate(
                max_upside=Max(
                    "reports__upside",
                    filter=Q(reports__as_of_timestamp__gte=start_7d, reports__upside__isnull=False),
                )
            )
            .filter(max_upside__isnull=False)
            .select_related()  # no-op but harmless
            .order_by("-max_upside")[: self.TOP_N_UPSIDE]
        )

        top_upside_30d = (
            Stock.objects.annotate(
                max_upside=Max(
                    "reports__upside",
                    filter=Q(reports__as_of_timestamp__gte=start_30d, reports__upside__isnull=False),
                )
            )
            .filter(max_upside__isnull=False)
            .order_by("-max_upside")[: self.TOP_N_UPSIDE]
        )

        # -------------
        # 2) Most reported on (30d / 365d)
        # -------------
        most_reported_30d = (
            Stock.objects.annotate(
                report_count=Count(
                    "reports",
                    filter=Q(reports__as_of_timestamp__gte=start_30d),
                )
            )
            .filter(report_count__gt=0)
            .order_by("-report_count", "ticker")[: self.TOP_N_MOST_REPORTED]
        )

        most_reported_365d = (
            Stock.objects.annotate(
                report_count=Count(
                    "reports",
                    filter=Q(reports__as_of_timestamp__gte=start_365d),
                )
            )
            .filter(report_count__gt=0)
            .order_by("-report_count", "ticker")[: self.TOP_N_MOST_REPORTED]
        )

        # -------------
        # 3) "Most recent stocks that changed from BUY or NEUTRAL to UNDERPERFORM"
        # We'll interpret as:
        # - Find UNDERPERFORM reports
        # - Look at the immediately previous report for that stock
        # - If previous rating in (BUY, NEUTRAL), include it
        # - Take the 5 most recent such events
        #
        # This is efficient and pure SQL using Subquery.
        # -------------
        prev_rating_sq = (
            DailyReport.objects.filter(
                stock=OuterRef("stock"),
                as_of_timestamp__lt=OuterRef("as_of_timestamp"),
            )
            .order_by("-as_of_timestamp")
            .values("rating")[:1]
        )

        recent_downgrades = (
            DailyReport.objects.annotate(
                prev_rating=Coalesce(Subquery(prev_rating_sq), Value("")),
            )
            .filter(
                rating="UNDERPERFORM",
                prev_rating__in=["BUY", "NEUTRAL"],
            )
            .select_related("stock")
            .order_by("-as_of_timestamp")[:5]
        )

        # -------------
        # Optional chart data for "most reported" stocks (30d and 365d)
        # We'll build per-stock time series of price and price_objective.
        # -------------
        chart_stocks_30d = list(most_reported_30d[: self.CHART_STOCKS_COUNT])
        chart_stocks_365d = list(most_reported_365d[: self.CHART_STOCKS_COUNT])

        chart_series_30d = self._build_price_series(chart_stocks_30d, start_30d)
        chart_series_365d = self._build_price_series(chart_stocks_365d, start_365d)

        ctx.update(
            {
                "top_upside_7d": top_upside_7d,
                "top_upside_30d": top_upside_30d,
                "most_reported_30d": most_reported_30d,
                "most_reported_365d": most_reported_365d,
                "recent_downgrades": recent_downgrades,
                # JSON for charts
                "chart_stocks_30d": chart_stocks_30d,
                "chart_stocks_365d": chart_stocks_365d,
                "chart_series_30d_json": json.dumps(chart_series_30d),
                "chart_series_365d_json": json.dumps(chart_series_365d),
            }
        )
        return ctx

    def _build_price_series(self, stocks, start_dt):
        """
        Returns:
          { "<stock_id>": [{"t": "2026-01-16T13:48:00Z", "price": 123.45, "po": 150.0}, ...], ... }
        Only includes points where at least one of price/price_objective exists.
        """
        if not stocks:
            return {}

        stock_ids = [s.id for s in stocks]

        qs = (
            DailyReport.objects.filter(
                stock_id__in=stock_ids,
                as_of_timestamp__gte=start_dt,
            )
            .exclude(Q(price__isnull=True) & Q(price_objective__isnull=True))
            .order_by("stock_id", "as_of_timestamp")
            .values("stock_id", "as_of_timestamp", "price", "price_objective")
        )

        series = {str(sid): [] for sid in stock_ids}
        for row in qs:
            sid = str(row["stock_id"])
            series[sid].append(
                {
                    "t": row["as_of_timestamp"].isoformat(),
                    "price": float(row["price"]) if row["price"] is not None else None,
                    "po": float(row["price_objective"]) if row["price_objective"] is not None else None,
                }
            )

        # Cap points per stock to keep page light
        for sid, points in series.items():
            if len(points) > self.CHART_MAX_POINTS:
                series[sid] = points[-self.CHART_MAX_POINTS :]

        return series