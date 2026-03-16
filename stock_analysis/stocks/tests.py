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
        user = get_user_model().objects.create_user(username="investor", password="S3cur3Pass123!!")
        self.client.force_login(user)

        now = timezone.now()
        aapl = Stock.objects.create(ticker="AAPL", region="US", company_name="Apple Inc.")
        msft = Stock.objects.create(ticker="MSFT", region="US", company_name="Microsoft Corp.")

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
        self.assertContains(response, reverse("stock_detail", args=[aapl.id]))
        self.assertContains(response, reverse("stock_detail", args=[msft.id]))

        self.assertEqual(len(response.context["holdings_rows"]), 1)
        self.assertEqual(len(response.context["watchlist_rows"]), 2)
        self.assertEqual(len(response.context["report_windows"]), 3)

    def test_stock_detail_page_shows_chart_and_reports(self):
        stock = Stock.objects.create(ticker="NVDA", region="US", company_name="NVIDIA Corp.")
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
