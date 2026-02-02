from django.conf import settings
from django.db import models
from django.utils import timezone


class InvestorProfile(models.Model):
    """
    Optional but useful: a place to hang investor-specific fields later.
    Keeps you on built-in auth.User.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investor_profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Profile of {self.user.username}"


class Watch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watches",
    )
    stock = models.ForeignKey(
        "stocks.Stock",
        on_delete=models.CASCADE,
        related_name="watched_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "stock"], name="uniq_watch_user_stock"),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["stock"]),
        ]

    def __str__(self) -> str:
        return f"Watch<{self.user_id} -> {self.stock_id}>"


class HoldingSnapshot(models.Model):
    """
    Append-only: never update, only insert a new row when user changes holdings.
    Represents the user's position in a stock 'as of' a timestamp.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="holding_snapshots",
    )
    stock = models.ForeignKey(
        "stocks.Stock",
        on_delete=models.CASCADE,
        related_name="holding_snapshots",
    )

    as_of = models.DateTimeField(default=timezone.now, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # Shares/units held. Allow decimals to support fractional shares.
    quantity = models.DecimalField(max_digits=24, decimal_places=6)

    # Optional: average cost basis per share (or total cost basis — choose one convention).
    avg_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)

    notes = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["user", "stock", "-as_of"]),
            models.Index(fields=["user", "-as_of"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "stock", "as_of"], name="uniq_snap_user_stock_as_of"),
        ]

    def __str__(self) -> str:
        return f"Snapshot<{self.user_id} {self.stock_id} qty={self.quantity} @ {self.as_of:%Y-%m-%d}>"
