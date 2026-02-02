from django.contrib import admin
from .models import Stock, DailyReport, ReportKeyTakeaway, EPSForecast

# Register your models here.
@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'region', 'company_name', 'currency_code']
    search_fields = ["ticker", "company_name"]
    list_filter = ["region", "currency_code"]
    ordering = ["ticker",]

    inlines = []

class EPSForecastInline(admin.TabularInline):
    model = EPSForecast
    extra = 0

class ReportKeyTakeawayInline(admin.TabularInline):
    model = ReportKeyTakeaway
    extra = 0

@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "as_of_timestamp",
        "rating",
        "price",
        "price_objective",
        "created_at",
    )

    list_select_related = ("stock",)

    list_filter = (
        "rating",
        "stock__region",
    )

    search_fields = (
        "stock__ticker",
        "stock__company_name",
        "analyst_team",
        "blurb",
    )

    autocomplete_fields = ["stock"]

    ordering = ("-as_of_timestamp",)

    readonly_fields = ("created_at",)

    inlines = [
        EPSForecastInline,
        ReportKeyTakeawayInline,
    ]
