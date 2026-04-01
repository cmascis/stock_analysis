from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import InvestorProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    # When loading fixtures, Django saves with raw=True. Skip signal to avoid duplicates.
    if kwargs.get("raw", False):
        return

    if created:
        InvestorProfile.objects.get_or_create(user=instance)
