import signal
import time
from datetime import timedelta
from zoneinfo import ZoneInfoNotFoundError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from stocks.ingestion.runner import (
    IngestionError,
    enqueue_run,
    execute_run,
    heartbeat,
    recover_interrupted_runs,
    worker_lock,
)
from stocks.ingestion.schedule import daily_schedule, daily_sync_due
from stocks.models import IngestionRun, IngestionWorker


class Command(BaseCommand):
    help = "Process queued report syncs and sync daily at 11:00 and 17:00 Eastern by default."

    def add_arguments(self, parser):
        schedule = parser.add_mutually_exclusive_group()
        schedule.add_argument(
            "--interval",
            type=int,
            default=None,
            help="Override daily scheduling with an interval in seconds; 0 processes only staff-queued runs.",
        )
        schedule.add_argument(
            "--times",
            default=settings.BOFA_SYNC_TIMES,
            help="Comma-separated daily HH:MM times (default: 11:00,17:00).",
        )
        parser.add_argument(
            "--timezone",
            default=settings.BOFA_SYNC_TIMEZONE,
            help="Timezone for daily runs (default: America/New_York).",
        )
        parser.add_argument(
            "--once", action="store_true", help="Process at most one run and exit."
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval is not None and interval < 0:
            raise CommandError("--interval must be nonnegative")
        try:
            slots, zone = (
                daily_schedule(options["times"], options["timezone"])
                if interval is None
                else (None, None)
            )
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise CommandError(
                "Invalid daily schedule: use HH:MM times and a valid IANA timezone."
            ) from error
        self.stopping = False
        previous = {}

        def stop(signum, frame):
            self.stopping = True

        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, stop)
        try:
            with worker_lock():
                recover_interrupted_runs()
                self.stdout.write(
                    f"Report ingestion worker started ({options['times']} {options['timezone']})."
                    if interval is None
                    else f"Report ingestion worker started (interval={interval}s)."
                )
                while not self.stopping:
                    heartbeat()
                    run = IngestionRun.objects.filter(
                        status=IngestionRun.Status.QUEUED
                    ).first()
                    last = IngestionRun.objects.filter(
                        dry_run=False, message_limit=0
                    ).first()
                    now = timezone.now()
                    due = (
                        daily_sync_due(
                            now, last.queued_at if last else None, slots, zone
                        )
                        if interval is None
                        else bool(
                            interval
                            and (
                                last is None
                                or (last.finished_at or last.queued_at)
                                <= now - timedelta(seconds=interval)
                            )
                        )
                    )
                    if run is None and due:
                        run, _ = enqueue_run()
                    if run:
                        try:
                            execute_run(run)
                        except IngestionError as error:
                            self.stderr.write(f"Sync #{run.pk} failed: {error}")
                            if options["once"]:
                                raise CommandError(str(error)) from error
                        else:
                            self.stdout.write(
                                f"Sync #{run.pk} completed; created {run.reports_created} reports."
                            )
                    if options["once"]:
                        break
                    time.sleep(2)
                IngestionWorker.objects.filter(pk=1).delete()
        except IngestionError as error:
            raise CommandError(str(error)) from error
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
