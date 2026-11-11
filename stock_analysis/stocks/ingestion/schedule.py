"""Wall-clock scheduling for the report worker in its configured timezone."""

from datetime import datetime
from zoneinfo import ZoneInfo


def daily_schedule(times, timezone_name):
    zone = ZoneInfo(timezone_name)
    slots = sorted(
        {datetime.strptime(value.strip(), "%H:%M").time() for value in times.split(",")}
    )
    if not slots:
        raise ValueError("At least one daily sync time is required")
    return slots, zone


def daily_sync_due(now, last_queued_at, slots, zone):
    local_now = now.astimezone(zone)
    elapsed = [
        datetime.combine(local_now.date(), slot, tzinfo=zone)
        for slot in slots
        if slot <= local_now.time()
    ]
    if not elapsed:
        return False
    return last_queued_at is None or last_queued_at < elapsed[-1]
