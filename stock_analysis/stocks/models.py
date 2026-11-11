import re
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone


class UppercaseCharField(models.CharField):
    def normalize(self, value):
        value = super().to_python(value)
        if value in ("", None):
            return value
        return value.strip().upper()

    def to_python(self, value):
        return self.normalize(value)

    def get_prep_value(self, value):
        return super().get_prep_value(self.normalize(value))

    def pre_save(self, model_instance, add):
        value = self.normalize(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, value)
        return value


class NormalizedRatingField(models.CharField):
    _ws = re.compile(r"\s+")

    def normalize(self, value):
        value = super().to_python(value)
        if value in ("", None):
            return value
        value = value.strip().upper()
        return self._ws.sub("_", value)

    def to_python(self, value):
        return self.normalize(value)

    def get_prep_value(self, value):
        return super().get_prep_value(self.normalize(value))

    def pre_save(self, model_instance, add):
        value = self.normalize(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, value)
        return value


class Stock(models.Model):
    """
    Example: AAPL, region 'US'.
    Decide what uniquely identifies a 'stock' in your system.
    """

    ticker = UppercaseCharField(max_length=16)
    region = UppercaseCharField(max_length=8, default="US")
    company_name = models.CharField(max_length=255)

    currency_code = UppercaseCharField(max_length=3, default="USD")

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["ticker", "region"], name="uniq_stock_ticker_region"
            ),
        )
        indexes = (models.Index(fields=["ticker", "region"]),)

    def __str__(self) -> str:
        return f"{self.ticker} {self.region}"


class DailyReport(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="reports")
    ingestion_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)

    link = models.URLField(max_length=500, blank=True, default="")
    as_of_timestamp = models.DateTimeField(
        default=timezone.now
    )  # as of date for report
    created_at = models.DateTimeField(auto_now_add=True)  # upon creation in database
    blurb = models.TextField(blank=True, default="")

    rating = NormalizedRatingField(max_length=20, blank=True, default="")
    analyst_team = models.CharField(max_length=128, blank=True, default="")

    report_subtitle = models.CharField(max_length=255, blank=True, default="")

    # list[str]
    raw_text = models.JSONField(default=list, blank=True)

    # Money/metrics: store as raw numeric values in actual currency units.
    # Use DecimalField for safety; pick max_digits generously.
    price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    price_objective = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )

    # Upside as a fraction (e.g. 0.1234 = 12.34%) OR store percent.
    upside = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    average_daily_value = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True
    )
    market_cap = models.DecimalField(
        max_digits=28, decimal_places=2, null=True, blank=True
    )

    class Meta:
        indexes = (
            models.Index(fields=["stock", "-as_of_timestamp"]),
            models.Index(fields=["stock", "rating", "-as_of_timestamp"]),
        )
        ordering: ClassVar[list[str]] = ["-as_of_timestamp"]
        constraints = (
            models.UniqueConstraint(
                fields=["stock", "as_of_timestamp"],
                name="uniq_report_as_of_timestamp_per_stock",
            ),
        )

    def __str__(self) -> str:
        return f"{self.stock} @ {self.as_of_timestamp:%Y-%m-%d %H:%M}"


class ReportKeyTakeaway(models.Model):
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name="key_takeaways",
    )
    order = models.PositiveSmallIntegerField()  # 0-based or 1-based, your choice
    text = models.TextField()

    class Meta:
        ordering: ClassVar[list[str]] = ["order"]
        constraints = (
            models.UniqueConstraint(
                fields=["report", "order"],
                name="uniq_takeaway_order_per_report",
            ),
        )
        indexes = (models.Index(fields=["report", "order"]),)

    def __str__(self) -> str:
        return f"{self.report} takeaway #{self.order}: {self.text}"


class EPSForecast(models.Model):
    report = models.ForeignKey(
        DailyReport, on_delete=models.CASCADE, related_name="eps_forecasts"
    )
    year = models.PositiveSmallIntegerField()
    eps = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["report", "year"], name="uniq_eps_year_per_report"
            ),
        )
        indexes = (
            models.Index(fields=["year"]),
            models.Index(fields=["report", "year"]),
        )

    def __str__(self) -> str:
        return f"{self.report} {self.year} EPS={self.eps}"


class IngestionRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    status = models.CharField(max_length=12, choices=Status, default=Status.QUEUED)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    queued_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    stage = models.CharField(max_length=100, blank=True)
    message_limit = models.PositiveIntegerField(default=0)
    dry_run = models.BooleanField(default=False)
    messages_found = models.PositiveIntegerField(default=0)
    messages_processed = models.PositiveIntegerField(default=0)
    messages_skipped = models.PositiveIntegerField(default=0)
    messages_failed = models.PositiveIntegerField(default=0)
    reports_created = models.PositiveIntegerField(default=0)
    reports_skipped = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-queued_at", "-pk"]
        constraints = (
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(status__in=["queued", "running"]),
                name="uniq_active_ingestion_run",
            ),
        )

    def __str__(self):
        return f"Report sync #{self.pk} ({self.get_status_display()})"


class IngestionMessage(models.Model):
    source_key = models.CharField(max_length=64, unique=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_run = models.ForeignKey(IngestionRun, null=True, on_delete=models.SET_NULL)
    error = models.CharField(max_length=255, blank=True)


class IngestionWorker(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    heartbeat_at = models.DateTimeField(default=timezone.now)
