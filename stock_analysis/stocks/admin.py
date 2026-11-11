from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse
from django.views.decorators.http import require_POST

from .ingestion.runner import enqueue_run, worker_online
from .models import (
    DailyReport,
    EPSForecast,
    IngestionMessage,
    IngestionRun,
    ReportKeyTakeaway,
    Stock,
)


# Register your models here.
@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("ticker", "region", "company_name", "currency_code")
    search_fields = ("ticker", "company_name")
    list_filter = ("region", "currency_code")
    ordering = ("ticker",)

    inlines = ()


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

    autocomplete_fields = ("stock",)

    ordering = ("-as_of_timestamp",)

    readonly_fields = ("created_at",)

    inlines = (
        EPSForecastInline,
        ReportKeyTakeawayInline,
    )


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/stocks/ingestionrun/change_list.html"
    list_display = (
        "id",
        "status",
        "stage",
        "queued_at",
        "finished_at",
        "reports_created",
        "messages_failed",
        "requested_by",
    )
    list_filter = ("status", "dry_run")
    list_select_related = ("requested_by",)
    readonly_fields = tuple(field.name for field in IngestionRun._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [
            path(
                "sync/",
                self.admin_site.admin_view(require_POST(self.sync)),
                name="stocks_ingestionrun_sync",
            )
        ] + super().get_urls()

    def sync(self, request):
        if not request.user.has_perm("stocks.add_ingestionrun"):
            raise PermissionDenied
        run, created = enqueue_run(user=request.user)
        self.message_user(
            request,
            f"Sync #{run.pk} queued."
            if created
            else f"Sync #{run.pk} is already {run.get_status_display().lower()}.",
            messages.SUCCESS if created else messages.INFO,
        )
        return redirect("admin:stocks_ingestionrun_changelist")

    def changelist_view(self, request, extra_context=None):
        context = {
            **(extra_context or {}),
            "worker_online": worker_online(),
            "can_sync": request.user.has_perm("stocks.add_ingestionrun"),
            "message_checkpoints_url": reverse(
                "admin:stocks_ingestionmessage_changelist"
            ),
        }
        return super().changelist_view(request, extra_context=context)


@admin.register(IngestionMessage)
class IngestionMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "last_run", "completed_at", "error")
    list_filter = ("completed_at",)
    readonly_fields = tuple(field.name for field in IngestionMessage._meta.fields)
    list_select_related = ("last_run",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
