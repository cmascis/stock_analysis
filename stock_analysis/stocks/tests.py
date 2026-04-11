from decimal import Decimal
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from investor.models import HoldingSnapshot, Watch
from stocks.models import DailyReport, Stock


class HomeViewTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock Analysis")

    def test_signed_in_home_shows_dashboard_data(self):
        user = get_user_model().objects.create_user(
            username="investor", password="S3cur3Pass123!!"
        )
        self.client.force_login(user)

        now = timezone.now()
        aapl = Stock.objects.create(
            ticker="AAPL", region="US", company_name="Apple Inc."
        )
        msft = Stock.objects.create(
            ticker="MSFT", region="US", company_name="Microsoft Corp."
        )

        HoldingSnapshot.objects.create(
            user=user,
            stock=aapl,
            as_of=now - timedelta(days=1),
            quantity=Decimal("12.5000"),
            avg_cost=Decimal("180.00"),
        )
        Watch.objects.create(user=user, stock=aapl)
        Watch.objects.create(user=user, stock=msft)

        DailyReport.objects.create(
            stock=aapl,
            as_of_timestamp=now - timedelta(days=3),
            price=Decimal("191.50"),
            price_objective=Decimal("202.00"),
            upside=Decimal("0.0540"),
            rating="HOLD",
        )
        DailyReport.objects.create(
            stock=aapl,
            as_of_timestamp=now - timedelta(hours=2),
            price=Decimal("194.00"),
            price_objective=Decimal("214.00"),
            upside=Decimal("0.1031"),
            rating="BUY",
        )
        DailyReport.objects.create(
            stock=msft,
            as_of_timestamp=now - timedelta(hours=10),
            price=Decimal("401.00"),
            price_objective=Decimal("430.00"),
            upside=Decimal("0.0723"),
            rating="BUY",
        )
        DailyReport.objects.create(
            stock=msft,
            as_of_timestamp=now - timedelta(hours=1),
            price=Decimal("405.00"),
            price_objective=Decimal("445.00"),
            upside=Decimal("0.0987"),
            rating="BUY",
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portfolio Snapshot vs Latest Reports")
        self.assertContains(response, "Most Recent Watchlist Updates")
        self.assertContains(response, "Report Leaders by Time Window")
        self.assertContains(response, "AAPL US")
        self.assertContains(response, "MSFT US")
        self.assertContains(response, "Latest Report")
        self.assertContains(response, "Latest report")
        self.assertContains(response, reverse("stock_detail", args=[aapl.id]))
        self.assertContains(response, reverse("stock_detail", args=[msft.id]))

        self.assertEqual(len(response.context["holdings_rows"]), 1)
        self.assertEqual(len(response.context["watchlist_rows"]), 2)
        self.assertEqual(len(response.context["report_windows"]), 3)

    def test_home_dashboard_uses_latest_non_null_report_per_field(self):
        user = get_user_model().objects.create_user(
            username="provenance", password="S3cur3Pass123!!"
        )
        self.client.force_login(user)

        now = timezone.now()
        stock = Stock.objects.create(
            ticker="ACME",
            region="US",
            company_name="Acme Holdings",
            currency_code="USD",
        )
        HoldingSnapshot.objects.create(
            user=user,
            stock=stock,
            as_of=now - timedelta(days=1),
            quantity=Decimal("10.0000"),
            avg_cost=Decimal("88.00"),
        )
        Watch.objects.create(user=user, stock=stock)

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=5),
            price=Decimal("90.00"),
            price_objective=Decimal("120.00"),
            upside=Decimal("0.2000"),
            rating="HOLD",
        )
        mid_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=None,
            price_objective=Decimal("135.00"),
            upside=None,
            rating="",
        )
        latest_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(hours=1),
            price=Decimal("100.00"),
            price_objective=None,
            upside=Decimal("0.1000"),
            rating="BUY",
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "From report")
        self.assertContains(response, "Latest Report")
        self.assertContains(response, "Latest report")

        holdings_row = response.context["holdings_rows"][0]
        self.assertEqual(holdings_row["price"], Decimal("100.000000"))
        self.assertEqual(holdings_row["price_as_of"], latest_report.as_of_timestamp)
        self.assertEqual(holdings_row["price_objective"], Decimal("135.000000"))
        self.assertEqual(
            holdings_row["price_objective_as_of"], mid_report.as_of_timestamp
        )
        self.assertEqual(holdings_row["upside_pct"], Decimal("10.000000"))
        self.assertEqual(holdings_row["upside_as_of"], latest_report.as_of_timestamp)
        self.assertEqual(holdings_row["rating"], "BUY")
        self.assertEqual(holdings_row["rating_as_of"], latest_report.as_of_timestamp)
        self.assertEqual(holdings_row["report_at"], latest_report.as_of_timestamp)

        watchlist_row = response.context["watchlist_rows"][0]
        self.assertEqual(watchlist_row["price"], Decimal("100.000000"))
        self.assertEqual(watchlist_row["price_as_of"], latest_report.as_of_timestamp)
        self.assertEqual(watchlist_row["price_objective"], Decimal("135.000000"))
        self.assertEqual(
            watchlist_row["price_objective_as_of"], mid_report.as_of_timestamp
        )
        self.assertEqual(watchlist_row["upside_pct"], Decimal("10.000000"))
        self.assertEqual(watchlist_row["upside_as_of"], latest_report.as_of_timestamp)
        self.assertEqual(watchlist_row["rating"], "BUY")
        self.assertEqual(watchlist_row["rating_as_of"], latest_report.as_of_timestamp)
        self.assertEqual(watchlist_row["report_at"], latest_report.as_of_timestamp)

    def test_home_report_leaders_includes_upgrade_and_downgrade(self):
        user = get_user_model().objects.create_user(
            username="leaders_delta", password="S3cur3Pass123!!"
        )
        self.client.force_login(user)
        now = timezone.now()

        upgrade_stock = Stock.objects.create(
            ticker="UP1",
            region="US",
            company_name="Upgrade Name",
            currency_code="USD",
        )
        downgrade_stock = Stock.objects.create(
            ticker="DOWN1",
            region="US",
            company_name="Downgrade Name",
            currency_code="USD",
        )

        DailyReport.objects.create(
            stock=upgrade_stock,
            as_of_timestamp=now - timedelta(days=10),
            price_objective=Decimal("100.00"),
        )
        DailyReport.objects.create(
            stock=upgrade_stock,
            as_of_timestamp=now - timedelta(hours=3),
            price_objective=Decimal("140.00"),
            upside=Decimal("0.1200"),
        )

        DailyReport.objects.create(
            stock=downgrade_stock,
            as_of_timestamp=now - timedelta(days=8),
            price_objective=Decimal("250.00"),
        )
        DailyReport.objects.create(
            stock=downgrade_stock,
            as_of_timestamp=now - timedelta(hours=2),
            price_objective=Decimal("190.00"),
            upside=Decimal("0.0900"),
        )

        response = self.client.get(reverse("home"))
        window = response.context["report_windows"][0]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Largest objective downgrade")
        self.assertIsNotNone(window["largest_upgrade"])
        self.assertEqual(window["largest_upgrade"]["stock"].id, upgrade_stock.id)
        self.assertEqual(window["largest_upgrade"]["upgrade_amount"], Decimal("40"))
        self.assertIsNotNone(window["largest_downgrade"])
        self.assertEqual(window["largest_downgrade"]["stock"].id, downgrade_stock.id)
        self.assertEqual(window["largest_downgrade"]["downgrade_amount"], Decimal("60"))

    def test_stock_detail_page_shows_chart_and_reports(self):
        stock = Stock.objects.create(
            ticker="NVDA", region="US", company_name="NVIDIA Corp."
        )
        now = timezone.now()
        first_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=Decimal("900.00"),
            price_objective=Decimal("980.00"),
            upside=Decimal("0.0888"),
            rating="BUY",
            blurb="First report blurb.",
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("915.00"),
            price_objective=Decimal("1010.00"),
            upside=Decimal("0.1038"),
            rating="BUY",
            blurb="Second report blurb.",
        )
        first_report.key_takeaways.create(order=0, text="Demand remains strong.")

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Price Objective Over Time")
        self.assertContains(response, "Report Timeline")
        self.assertContains(response, "Second report blurb.")
        self.assertContains(response, "Demand remains strong.")
        self.assertContains(response, "objective-chart")
        self.assertContains(response, "data-report-select")
        self.assertContains(response, "price-points")
        self.assertContains(response, "price-continuation-points")
        self.assertContains(response, "objective-continuation-points")

    def test_stock_detail_uses_latest_available_metric_values_per_field(self):
        stock = Stock.objects.create(
            ticker="ACME", region="US", company_name="Acme Holdings"
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=4),
            price=Decimal("91.00"),
            price_objective=Decimal("120.00"),
            upside=Decimal("0.0500"),
            rating="NEUTRAL",
        )
        latest_price_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=Decimal("103.25"),
            price_objective=None,
            rating="",
        )
        latest_objective_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(hours=12),
            price=None,
            price_objective=Decimal("135.50"),
            upside=Decimal("0.1250"),
            rating="BUY",
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["latest_price"], Decimal("103.250000"))
        self.assertEqual(
            response.context["latest_price_as_of"], latest_price_report.as_of_timestamp
        )
        self.assertEqual(
            response.context["latest_price_objective"], Decimal("135.500000")
        )
        self.assertEqual(
            response.context["latest_price_objective_as_of"],
            latest_objective_report.as_of_timestamp,
        )
        self.assertEqual(response.context["latest_upside_pct"], Decimal("12.500000"))
        self.assertEqual(
            response.context["latest_upside_as_of"],
            latest_objective_report.as_of_timestamp,
        )
        self.assertEqual(response.context["latest_rating"], "BUY")
        self.assertEqual(response.context["latest_rating_display"], "Buy")
        self.assertEqual(
            response.context["latest_rating_as_of"],
            latest_objective_report.as_of_timestamp,
        )
        self.assertEqual(response.context["previous_rating"], "NEUTRAL")
        self.assertEqual(response.context["previous_rating_display"], "Neutral")
        self.assertEqual(
            response.context["rating_change_summary"], "Upgraded from Neutral"
        )
        self.assertContains(response, "Latest Rating")
        self.assertContains(response, "Latest Upside")
        self.assertContains(response, "$103.25")
        self.assertContains(response, "$135.50")
        self.assertContains(response, "12.50%")
        self.assertContains(response, "Buy")
        self.assertContains(response, "<strong>Acme Holdings | Buy</strong>", html=True)
        self.assertContains(response, "Upgraded from Neutral")

    def test_stock_detail_objective_change_uses_latest_different_objective(self):
        stock = Stock.objects.create(
            ticker="GOOG", region="US", company_name="Alphabet Inc."
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=5),
            price_objective=Decimal("100.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price_objective=Decimal("130.00"),
        )
        latest_objective_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price_objective=Decimal("130.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(hours=2),
            price=Decimal("111.00"),
            rating="BUY",
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["objective_change"], Decimal("30.000000"))
        self.assertEqual(response.context["objective_change_pct"], Decimal("30.00"))
        self.assertEqual(
            response.context["previous_different_objective"], Decimal("100.000000")
        )
        self.assertEqual(
            response.context["objective_change_as_of"],
            latest_objective_report.as_of_timestamp,
        )
        self.assertContains(response, "Objective Change")
        self.assertContains(response, "+$30.00")
        self.assertContains(response, "from $100.00: +30.00%")

    def test_stock_detail_objective_coverage_uses_latest_price_against_distinct_objectives(
        self,
    ):
        stock = Stock.objects.create(
            ticker="NFLX", region="US", company_name="Netflix Inc."
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=5),
            price_objective=Decimal("100.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=4),
            price_objective=Decimal("100.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=3),
            price_objective=Decimal("120.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price_objective=Decimal("150.00"),
        )
        latest_price_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("130.00"),
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        objective_coverage = response.context["objective_coverage"]
        self.assertEqual(objective_coverage["cleared_count"], 2)
        self.assertEqual(objective_coverage["total_count"], 3)
        self.assertEqual(objective_coverage["percentage"], Decimal("66.67"))
        self.assertEqual(
            objective_coverage["as_of"], latest_price_report.as_of_timestamp
        )
        self.assertEqual(
            objective_coverage["summary_text"],
            "Latest price at or above 2 of 3 distinct objectives",
        )
        self.assertContains(response, "Objectives Cleared")
        self.assertContains(response, "66.67%")
        self.assertContains(
            response, "Latest price at or above 2 of 3 distinct objectives"
        )

    def test_stock_detail_rating_card_shows_maintained_context(self):
        stock = Stock.objects.create(
            ticker="SHOP", region="US", company_name="Shopify Inc."
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=3),
            rating="BUY",
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=Decimal("88.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            rating="BUY",
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["rating_change_summary"], "Maintained at Buy")
        self.assertContains(response, "Maintained at Buy")

    def test_stock_detail_rating_card_shows_downgraded_context(self):
        stock = Stock.objects.create(
            ticker="CRM", region="US", company_name="Salesforce Inc."
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=3),
            rating="BUY",
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            rating="NEUTRAL",
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["rating_change_summary"], "Downgraded from Buy"
        )
        self.assertContains(response, "Downgraded from Buy")

    def test_stock_detail_chart_adds_dashed_continuation_for_stale_points(self):
        stock = Stock.objects.create(
            ticker="META", region="US", company_name="Meta Platforms"
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=4),
            price=Decimal("480.00"),
            price_objective=Decimal("560.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("505.00"),
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        chart_price_points = response.context["chart_price_points"]
        chart_objective_points = response.context["chart_objective_points"]
        chart_price_continuation_points = response.context[
            "chart_price_continuation_points"
        ]
        chart_objective_continuation_points = response.context[
            "chart_objective_continuation_points"
        ]
        chart_x_max = response.context["chart_x_max"]

        self.assertEqual(len(chart_price_points), 2)
        self.assertEqual(len(chart_objective_points), 1)
        self.assertEqual(len(chart_price_continuation_points), 2)
        self.assertEqual(len(chart_objective_continuation_points), 2)
        self.assertEqual(chart_price_continuation_points[-1]["x"], chart_x_max)
        self.assertEqual(chart_objective_continuation_points[-1]["x"], chart_x_max)
        self.assertEqual(
            chart_price_continuation_points[0]["y"],
            chart_price_continuation_points[-1]["y"],
        )
        self.assertEqual(
            chart_objective_continuation_points[0]["y"],
            chart_objective_continuation_points[-1]["y"],
        )
        self.assertContains(response, "chart-x-max")
        self.assertContains(response, "objective-points")
        self.assertContains(response, "price-continuation-points")
        self.assertContains(response, "objective-continuation-points")

    def test_stock_detail_chart_skips_dashed_continuation_for_today_points(self):
        stock = Stock.objects.create(
            ticker="ORCL", region="US", company_name="Oracle Corp."
        )
        today_start = timezone.localtime().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=today_start - timedelta(days=2),
            price=Decimal("150.00"),
            price_objective=Decimal("165.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=today_start,
            price=Decimal("155.00"),
            price_objective=Decimal("170.00"),
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["chart_price_continuation_points"], [])
        self.assertEqual(response.context["chart_objective_continuation_points"], [])

    def test_stock_detail_defaults_analysis_window_to_earliest_report_and_today(self):
        stock = Stock.objects.create(
            ticker="AMD", region="US", company_name="Advanced Micro Devices"
        )
        now = timezone.now()
        earliest_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=7),
            price=Decimal("151.00"),
        )
        latest_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=Decimal("156.00"),
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_report_history"])
        self.assertEqual(
            response.context["earliest_report_date"],
            timezone.localdate(earliest_report.as_of_timestamp),
        )
        self.assertEqual(
            response.context["last_report_date"],
            timezone.localdate(latest_report.as_of_timestamp),
        )
        self.assertEqual(
            response.context["selected_start_date"],
            timezone.localdate(earliest_report.as_of_timestamp),
        )
        self.assertEqual(response.context["selected_end_date"], timezone.localdate())
        self.assertEqual(
            response.context["report_date_options"],
            [
                timezone.localdate(earliest_report.as_of_timestamp).isoformat(),
                timezone.localdate(latest_report.as_of_timestamp).isoformat(),
            ],
        )
        self.assertContains(response, "Analysis Window")
        self.assertContains(response, 'name="start_date"')
        self.assertContains(response, 'name="end_date"')
        self.assertContains(response, "data-analysis-window-form")
        self.assertContains(response, "Auto-applies after you leave a date field.")
        self.assertContains(response, "report-date-options")

    def test_stock_detail_analysis_window_waits_for_field_blur_before_submit(self):
        stock = Stock.objects.create(
            ticker="META", region="US", company_name="Meta Platforms"
        )
        now = timezone.now()
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=7),
            price=Decimal("505.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("517.00"),
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'startInput.addEventListener("change", markWindowChangePending);',
        )
        self.assertContains(
            response,
            'endInput.addEventListener("change", markWindowChangePending);',
        )
        self.assertContains(
            response,
            'startInput.addEventListener("blur", handleWindowBlur);',
        )
        self.assertContains(
            response,
            'endInput.addEventListener("blur", handleWindowBlur);',
        )
        self.assertNotContains(
            response,
            'startInput.addEventListener("input", syncDateInputs);',
        )
        self.assertNotContains(
            response,
            'endInput.addEventListener("input", syncDateInputs);',
        )
        self.assertNotContains(
            response,
            'startInput.addEventListener("change", handleWindowChange);',
        )
        self.assertNotContains(
            response,
            'endInput.addEventListener("change", handleWindowChange);',
        )

    def test_stock_detail_filters_reports_and_metrics_by_selected_window(self):
        stock = Stock.objects.create(
            ticker="INTC", region="US", company_name="Intel Corp."
        )
        now = timezone.now()
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=6),
            price=Decimal("88.00"),
            price_objective=Decimal("145.00"),
            upside=Decimal("0.2000"),
            rating="NEUTRAL",
            blurb="Old report blurb.",
        )
        mid_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=3),
            price=Decimal("97.00"),
            price_objective=Decimal("130.00"),
            upside=Decimal("0.1000"),
            rating="BUY",
            blurb="Mid window blurb.",
        )
        latest_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("101.00"),
            price_objective=None,
            upside=None,
            rating="",
            blurb="Latest window blurb.",
        )

        response = self.client.get(
            reverse("stock_detail", args=[stock.id]),
            {
                "start_date": timezone.localdate(
                    mid_report.as_of_timestamp
                ).isoformat(),
                "end_date": timezone.localdate(
                    latest_report.as_of_timestamp
                ).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["report_count"], 2)
        self.assertEqual(
            [report.pk for report in response.context["reports"]],
            [latest_report.pk, mid_report.pk],
        )
        self.assertEqual(response.context["latest_price"], Decimal("101.000000"))
        self.assertEqual(
            response.context["latest_price_objective"], Decimal("130.000000")
        )
        self.assertEqual(response.context["latest_upside_pct"], Decimal("10.000000"))
        self.assertEqual(response.context["latest_rating"], "BUY")
        self.assertEqual(len(response.context["chart_price_points"]), 2)
        self.assertEqual(len(response.context["chart_objective_points"]), 1)
        self.assertEqual(response.context["chart_data_point_count"], 2)
        self.assertContains(response, "Mid window blurb.")
        self.assertContains(response, "Latest window blurb.")
        self.assertNotContains(response, "Old report blurb.")

    def test_stock_detail_invalid_dates_fall_back_to_default_window(self):
        stock = Stock.objects.create(
            ticker="UBER", region="US", company_name="Uber Technologies"
        )
        now = timezone.now()
        earliest_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=9),
            price=Decimal("70.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=Decimal("77.00"),
        )

        response = self.client.get(
            reverse("stock_detail", args=[stock.id]),
            {"start_date": "not-a-date", "end_date": "still-not-a-date"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["selected_start_date"],
            timezone.localdate(earliest_report.as_of_timestamp),
        )
        self.assertEqual(response.context["selected_end_date"], timezone.localdate())
        self.assertEqual(response.context["report_count"], 2)

    def test_stock_detail_clamps_out_of_bounds_dates(self):
        stock = Stock.objects.create(
            ticker="TSM", region="US", company_name="Taiwan Semiconductor"
        )
        now = timezone.now()
        earliest_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=11),
            price=Decimal("140.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=4),
            price=Decimal("146.00"),
        )
        requested_start = timezone.localdate(
            earliest_report.as_of_timestamp
        ) - timedelta(days=30)
        requested_end = timezone.localdate() + timedelta(days=30)

        response = self.client.get(
            reverse("stock_detail", args=[stock.id]),
            {
                "start_date": requested_start.isoformat(),
                "end_date": requested_end.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["selected_start_date"],
            timezone.localdate(earliest_report.as_of_timestamp),
        )
        self.assertEqual(response.context["selected_end_date"], timezone.localdate())
        self.assertEqual(response.context["report_count"], 2)

    def test_stock_detail_reorders_reversed_bounds(self):
        stock = Stock.objects.create(
            ticker="ASML", region="US", company_name="ASML Holding"
        )
        now = timezone.now()
        earlier_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=6),
            price=Decimal("935.00"),
        )
        later_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price=Decimal("950.00"),
        )

        response = self.client.get(
            reverse("stock_detail", args=[stock.id]),
            {
                "start_date": timezone.localdate(
                    later_report.as_of_timestamp
                ).isoformat(),
                "end_date": timezone.localdate(
                    earlier_report.as_of_timestamp
                ).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["selected_start_date"],
            timezone.localdate(earlier_report.as_of_timestamp),
        )
        self.assertEqual(
            response.context["selected_end_date"],
            timezone.localdate(later_report.as_of_timestamp),
        )
        self.assertEqual(response.context["report_count"], 2)

    def test_stock_detail_gap_window_expands_to_surrounding_reports(self):
        stock = Stock.objects.create(
            ticker="SNOW", region="US", company_name="Snowflake Inc."
        )
        now = timezone.now()
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=10),
            price=Decimal("150.00"),
        )
        earlier_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=5),
            price=Decimal("160.00"),
        )
        later_report = DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("170.00"),
        )
        gap_date = timezone.localdate(now - timedelta(days=3))

        response = self.client.get(
            reverse("stock_detail", args=[stock.id]),
            {
                "start_date": gap_date.isoformat(),
                "end_date": gap_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["selected_start_date"],
            timezone.localdate(earlier_report.as_of_timestamp),
        )
        self.assertEqual(
            response.context["selected_end_date"],
            timezone.localdate(later_report.as_of_timestamp),
        )
        self.assertEqual(
            [report.pk for report in response.context["reports"]],
            [later_report.pk, earlier_report.pk],
        )

    def test_stock_detail_chart_uses_selected_end_date_boundary(self):
        stock = Stock.objects.create(
            ticker="AVGO", region="US", company_name="Broadcom Inc."
        )
        now = timezone.now()
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=5),
            price=Decimal("1320.00"),
            price_objective=Decimal("1400.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=3),
            price=Decimal("1345.00"),
        )
        selected_end_date = timezone.localdate(now - timedelta(days=2))

        response = self.client.get(
            reverse("stock_detail", args=[stock.id]),
            {
                "start_date": timezone.localdate(now - timedelta(days=5)).isoformat(),
                "end_date": selected_end_date.isoformat(),
            },
        )

        expected_end_exclusive = timezone.make_aware(
            datetime.combine(
                selected_end_date + timedelta(days=1),
                datetime.min.time(),
            ),
            timezone.get_current_timezone(),
        )
        expected_x_max = int(expected_end_exclusive.timestamp() * 1000) - 1

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["chart_x_max"], expected_x_max)
        self.assertEqual(
            response.context["chart_price_continuation_points"][-1]["x"],
            expected_x_max,
        )
        self.assertEqual(
            response.context["chart_objective_continuation_points"][-1]["x"],
            expected_x_max,
        )

    def test_stock_detail_without_reports_hides_analysis_window(self):
        stock = Stock.objects.create(
            ticker="PLTR", region="US", company_name="Palantir Technologies"
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_report_history"])
        self.assertEqual(response.context["report_count"], 0)
        self.assertContains(response, "No reports found for this stock yet.")
        self.assertNotContains(response, "Analysis Window")
        self.assertNotContains(response, 'name="start_date"')


class SearchViewTests(TestCase):
    def test_stock_search_endpoint_returns_ticker_and_company_matches(self):
        aapl = Stock.objects.create(
            ticker="AAPL", region="US", company_name="Apple Inc."
        )
        Stock.objects.create(ticker="MSFT", region="US", company_name="Microsoft Corp.")
        Stock.objects.create(ticker="APP", region="US", company_name="AppLovin Corp.")

        response = self.client.get(reverse("stock_search_suggestions"), {"q": "app"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        tickers = [item["ticker"] for item in payload["results"]]
        self.assertIn("AAPL", tickers)
        self.assertIn("APP", tickers)
        self.assertTrue(
            any(
                item["url"] == reverse("stock_detail", args=[aapl.id])
                for item in payload["results"]
            )
        )

    def test_home_header_does_not_render_advanced_search_ui(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-search-url="')
        self.assertNotContains(response, "data-advanced-url")
        self.assertNotContains(response, "Advanced Search")

    def test_retired_advanced_search_url_returns_not_found(self):
        response = self.client.get("/stocks/advanced-search/")

        self.assertEqual(response.status_code, 404)
