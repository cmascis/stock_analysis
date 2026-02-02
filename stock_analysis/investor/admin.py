from django.contrib import admin
from .models import InvestorProfile, Watch, HoldingSnapshot


@admin.register(InvestorProfile)
class InvestorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at",)


@admin.register(Watch)
class WatchAdmin(admin.ModelAdmin):
    list_display = ("user", "stock", "created_at")
    list_select_related = ("user", "stock")
    search_fields = ("user__username", "stock__ticker", "stock__company_name")
    autocomplete_fields = ("stock",)
    readonly_fields = ("created_at",)


@admin.register(HoldingSnapshot)
class HoldingSnapshotAdmin(admin.ModelAdmin):
    list_display = ("user", "stock", "quantity", "avg_cost", "as_of", "created_at")
    list_select_related = ("user", "stock")
    search_fields = ("user__username", "stock__ticker", "stock__company_name")
    autocomplete_fields = ("stock",)
    ordering = ("-as_of",)
    readonly_fields = ("created_at",)
