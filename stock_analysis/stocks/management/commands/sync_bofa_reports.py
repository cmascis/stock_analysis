from django.core.management.base import BaseCommand, CommandError

from stocks.ingestion.runner import (
    IngestionError,
    enqueue_run,
    execute_run,
    recover_interrupted_runs,
    worker_lock,
)


class Command(BaseCommand):
    help = "Fetch, extract, clean, and import BofA reports from Gmail."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Newest messages to inspect; 0 (default) checks all, fetching only unfinished messages.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Download and validate without importing or marking messages complete.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be nonnegative")
        try:
            with worker_lock():
                recover_interrupted_runs()
                run, new = enqueue_run(
                    limit=options["limit"], dry_run=options["dry_run"]
                )
                if not new and (
                    run.message_limit != options["limit"]
                    or run.dry_run != options["dry_run"]
                ):
                    raise CommandError(
                        "A different sync is already queued. Run the worker to process it first."
                    )
                execute_run(run)
        except IngestionError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Sync #{run.pk}: processed={run.messages_processed} skipped={run.messages_skipped} created={run.reports_created} duplicate/validated={run.reports_skipped} dry-run={run.dry_run}"
            )
        )
