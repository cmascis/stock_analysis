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
        self.assertContains(response, "price-values")


class SearchAndAdvancedViewTests(TestCase):
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

    def test_advanced_search_supports_filtering_and_priority_sorting(self):
        now = timezone.now()
        alpha = Stock.objects.create(
            ticker="AAA", region="US", company_name="Alpha Inc.", currency_code="USD"
        )
        beta = Stock.objects.create(
            ticker="BBB", region="US", company_name="Beta Corp.", currency_code="USD"
        )
        Stock.objects.create(
            ticker="CCC", region="CA", company_name="Canada Co.", currency_code="CAD"
        )

        DailyReport.objects.create(
            stock=alpha,
            as_of_timestamp=now - timedelta(days=3),
            price=Decimal("120.00"),
            price_objective=Decimal("155.00"),
            upside=Decimal("0.1800"),
            market_cap=Decimal("150000000.00"),
            average_daily_value=Decimal("12000000.00"),
            rating="BUY",
        )
        DailyReport.objects.create(
            stock=alpha,
            as_of_timestamp=now - timedelta(days=1),
            price_objective=Decimal("157.00"),
            upside=Decimal("0.1700"),
            rating="BUY",
        )
        DailyReport.objects.create(
            stock=beta,
            as_of_timestamp=now - timedelta(hours=2),
            price=Decimal("130.00"),
            price_objective=Decimal("160.00"),
            upside=Decimal("0.2300"),
            market_cap=Decimal("260000000.00"),
            average_daily_value=Decimal("22000000.00"),
            rating="BUY",
        )

        response = self.client.get(
            reverse("advanced_stock_search"),
            {
                "region": "US",
                "price_min": "100",
                "price_max": "135",
                "sort1_field": "price_objective",
                "sort1_dir": "desc",
            },
        )

        self.assertEqual(response.status_code, 200)
        rows = list(response.context["page_obj"].object_list)
        self.assertEqual([stock.ticker for stock in rows], ["BBB", "AAA"])
        alpha_row = next(stock for stock in rows if stock.ticker == "AAA")
        self.assertEqual(alpha_row.latest_price, Decimal("120.000000"))
        self.assertEqual(
            alpha_row.latest_price_as_of.date(), (now - timedelta(days=3)).date()
        )
        self.assertContains(response, "Current Query Priority")
        self.assertContains(response, "Region contains")
        self.assertContains(response, "Price between")

    def test_advanced_search_default_ordering_is_recent_then_high_upside(self):
        now = timezone.now()
        first = Stock.objects.create(
            ticker="FIRST", region="US", company_name="First Corp."
        )
        second = Stock.objects.create(
            ticker="SECOND", region="US", company_name="Second Corp."
        )
        third = Stock.objects.create(
            ticker="THIRD", region="US", company_name="Third Corp."
        )

        DailyReport.objects.create(
            stock=first,
            as_of_timestamp=now - timedelta(hours=1),
            price=Decimal("100.00"),
            price_objective=Decimal("110.00"),
            upside=Decimal("0.1000"),
        )
        DailyReport.objects.create(
            stock=second,
            as_of_timestamp=now - timedelta(hours=2),
            price=Decimal("100.00"),
            price_objective=Decimal("130.00"),
            upside=Decimal("0.3000"),
        )
        DailyReport.objects.create(
            stock=third,
            as_of_timestamp=now - timedelta(hours=1),
            price=Decimal("100.00"),
            price_objective=Decimal("125.00"),
            upside=Decimal("0.2500"),
        )

        response = self.client.get(reverse("advanced_stock_search"))

        self.assertEqual(response.status_code, 200)
        rows = list(response.context["page_obj"].object_list)
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(rows[0].ticker, "THIRD")
        self.assertEqual(rows[1].ticker, "FIRST")
        self.assertEqual(rows[2].ticker, "SECOND")
