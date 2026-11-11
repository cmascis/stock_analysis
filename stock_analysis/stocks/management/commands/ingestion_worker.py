import signal
import time
from datetime import timedelta

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
from stocks.models import IngestionRun, IngestionWorker


class Command(BaseCommand):
    help = "Process queued report syncs and schedule periodic runs. Keep this process running alongside the web app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=settings.BOFA_SYNC_INTERVAL,
            help="Seconds between scheduled syncs; 0 processes only staff-queued runs (default: 900).",
        )
        parser.add_argument(
            "--once", action="store_true", help="Process at most one run and exit."
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval < 0:
            raise CommandError("--interval must be nonnegative")
        self.stopping = False
        previous = {}

        def stop(signum, frame):
            self.stopping = True

        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, stop)
        try:
            with worker_lock():
                recover_interrupted_runs()
                self.stdout.write("Report ingestion worker started.")
                while not self.stopping:
                    heartbeat()
                    run = IngestionRun.objects.filter(
                        status=IngestionRun.Status.QUEUED
                    ).first()
                    last = IngestionRun.objects.filter(dry_run=False).first()
                    if (
                        run is None
                        and interval
                        and (
                            last is None
                            or (last.finished_at or last.queued_at)
                            <= timezone.now() - timedelta(seconds=interval)
                        )
                    ):
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
