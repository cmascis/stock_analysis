from decimal import Decimal
from datetime import timedelta

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
            rating="HOLD",
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
        self.assertEqual(response.context["latest_rating"], "BUY")
        self.assertEqual(
            response.context["latest_rating_as_of"],
            latest_objective_report.as_of_timestamp,
        )
        self.assertContains(response, "Latest Rating")
        self.assertContains(response, "$103.25")
        self.assertContains(response, "$135.50")
        self.assertContains(response, "Buy")

    def test_stock_detail_objective_change_uses_latest_two_objective_reports(self):
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
            price=Decimal("108.00"),
            rating="HOLD",
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
        self.assertEqual(
            response.context["objective_change_as_of"],
            latest_objective_report.as_of_timestamp,
        )
        self.assertContains(response, "Objective Change")
        self.assertContains(response, "+$30.00")

    def test_stock_detail_chart_extends_to_current_date_without_fabricated_points(self):
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
        chart_x_max = response.context["chart_x_max"]

        self.assertEqual(len(chart_price_points), 2)
        self.assertEqual(len(chart_objective_points), 1)
        self.assertGreater(chart_x_max, chart_price_points[-1]["x"])
        self.assertGreater(chart_x_max, chart_objective_points[-1]["x"])
        self.assertNotIn(chart_x_max, [point["x"] for point in chart_price_points])
        self.assertNotIn(chart_x_max, [point["x"] for point in chart_objective_points])
        self.assertContains(response, "chart-x-max")
        self.assertContains(response, "objective-points")

    def test_stock_detail_objective_track_record_shows_mixed_follow_through(self):
        stock = Stock.objects.create(
            ticker="TSLA", region="US", company_name="Tesla Inc."
        )
        now = timezone.now()

        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=6),
            price_objective=Decimal("100.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=5),
            price=Decimal("102.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=4),
            price_objective=Decimal("110.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=3),
            price=Decimal("104.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=2),
            price_objective=Decimal("120.00"),
        )
        DailyReport.objects.create(
            stock=stock,
            as_of_timestamp=now - timedelta(days=1),
            price=Decimal("118.00"),
        )

        response = self.client.get(reverse("stock_detail", args=[stock.id]))

        self.assertEqual(response.status_code, 200)
        objective_track_record = response.context["objective_track_record"]
        self.assertEqual(objective_track_record["status_label"], "Mixed follow-through")
        self.assertEqual(objective_track_record["status_tone"], "neutral")
        self.assertEqual(objective_track_record["met_count"], 1)
        self.assertEqual(objective_track_record["missed_count"], 1)
        self.assertEqual(objective_track_record["pending_count"], 1)
        self.assertEqual(objective_track_record["resolved_count"], 2)
        self.assertEqual(
            objective_track_record["summary_text"], "1 of 2 resolved objectives hit"
        )
        self.assertEqual(objective_track_record["pending_text"], "1 pending objective")
        self.assertContains(response, "Mixed follow-through")
        self.assertContains(response, "1 of 2 resolved objectives hit")
        self.assertContains(response, "1 pending objective")


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
