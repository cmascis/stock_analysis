"""Persistent checkpoints and a single PostgreSQL-locked ingestion runner."""

import hashlib
import json
import os
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import UTC, timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from ftfy import fix_text
from pypdf.errors import PdfReadError
from unidecode import unidecode

from stocks.models import IngestionMessage, IngestionRun, IngestionWorker
from stocks.report_import import TS_FORMAT, import_record, prepare_record

from .parsers import extract_company_data, extract_subpage_links
from .source import BofAClient, SourceError, accessible_link_from_pdf, open_mailbox

LOCK_ID = 1112491585
ACTIVE = [IngestionRun.Status.QUEUED, IngestionRun.Status.RUNNING]


class IngestionError(Exception):
    pass


def enqueue_run(*, user=None, limit=0, dry_run=False):
    if limit < 0:
        raise ValueError("Message limit must be nonnegative")
    existing = IngestionRun.objects.filter(status__in=ACTIVE).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            return IngestionRun.objects.create(
                requested_by=user, message_limit=limit, dry_run=dry_run
            ), True
    except IntegrityError:
        existing = IngestionRun.objects.filter(status__in=ACTIVE).first()
        if existing is None:
            raise
        return existing, False


@contextmanager
def worker_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise IngestionError("Another report ingestion worker is already running.")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])


def heartbeat():
    IngestionWorker.objects.update_or_create(
        pk=1, defaults={"heartbeat_at": timezone.now()}
    )


def worker_online():
    return IngestionWorker.objects.filter(
        pk=1, heartbeat_at__gte=timezone.now() - timedelta(minutes=2)
    ).exists()


def recover_interrupted_runs():
    # Only call while holding the session advisory lock. A live worker cannot
    # lose ownership merely because a slow PDF or a large digest takes time.
    IngestionRun.objects.filter(status=IngestionRun.Status.RUNNING).update(
        status=IngestionRun.Status.FAILED,
        finished_at=timezone.now(),
        stage="Interrupted",
        error="Worker stopped before completion. Start another sync to resume unfinished messages.",
    )


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def clean(value):
    if isinstance(value, dict):
        return {clean(key): clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, str):
        return unidecode(unicodedata.normalize("NFKC", fix_text(value)))
    return value


def safe_error(error):
    if isinstance(error, SourceError):
        return str(error)
    # requests exceptions may contain signed research URLs; never persist them.
    return f"{type(error).__name__}: ingestion failed. Check source availability and retry."


def progress(run, stage):
    run.stage = stage
    run.save()
    heartbeat()


def process_message(run, checkpoint, message, client):
    progress(run, "Downloading report PDF")
    link, report_date = message.report_link_and_date()
    pdf = client.download_pdf(link)
    digest = hashlib.sha256(pdf).hexdigest()
    checkpoint.pdf_sha256 = digest
    checkpoint.save(update_fields=["pdf_sha256"])
    if IngestionMessage.objects.filter(
        pdf_sha256=digest, completed_at__isnull=False
    ).exists():
        return 0, 0
    folder = settings.BOFA_INGESTION_DIR / digest
    atomic_write(folder / "report.pdf", pdf)
    progress(run, "Extracting accessible report")
    html_path = folder / "report.html"
    if not html_path.exists():
        atomic_write(
            html_path, client.html(accessible_link_from_pdf(pdf)).encode("utf-8")
        )
    links = extract_subpage_links(html_path.read_text(encoding="utf-8"))
    if not links:
        # Do not let a login/error page become a permanent successful cache.
        html_path.unlink()
        raise SourceError(
            "Accessible report has no company links; it may require login or a parser update."
        )
    records = []
    timestamp = report_date.astimezone(UTC).strftime(TS_FORMAT)
    for index, (_, url, stock) in enumerate(links, 1):
        progress(run, f"Extracting company {index} of {len(links)}")
        cache = (
            folder / "companies" / (hashlib.sha256(url.encode()).hexdigest() + ".html")
        )
        html = cache.read_text(encoding="utf-8") if cache.exists() else client.html(url)
        stock["Timestamp"] = timestamp
        try:
            record = clean(extract_company_data(html, stock))
            prepare_record(record)
        except ValueError, TypeError, ValidationError:
            cache.unlink(missing_ok=True)
            raise
        atomic_write(cache, html.encode("utf-8"))
        records.append(record)
    # A JSON file represents a complete, validated digest, never partial work.
    atomic_write(
        folder / "reports.json",
        json.dumps(records, ensure_ascii=True, indent=2).encode(),
    )
    prepared = [prepare_record(record) for record in records]
    progress(run, "Validating reports" if run.dry_run else "Importing reports")
    if run.dry_run:
        return 0, len(prepared)
    with transaction.atomic():
        created = sum(
            import_record(record, deduplicate_content=True) for record in prepared
        )
        checkpoint.completed_at = timezone.now()
        checkpoint.error = ""
        checkpoint.save()
    return created, len(prepared) - created


def execute_run(run):
    """Execute while the caller holds worker_lock; errors remain visible in history."""
    run.status = IngestionRun.Status.RUNNING
    run.started_at = timezone.now()
    progress(run, "Connecting to Gmail")
    try:
        with open_mailbox() as mailbox, BofAClient() as client:
            uids = mailbox.message_ids(run.message_limit)
            run.messages_found = len(uids)
            progress(run, "Checking message checkpoints")
            for uid in uids:
                key = mailbox.source_key(uid)
                checkpoint, _ = IngestionMessage.objects.get_or_create(
                    source_key=key, defaults={"last_run": run}
                )
                if checkpoint.completed_at:
                    run.messages_skipped += 1
                    progress(run, "Skipping completed message")
                    continue
                checkpoint.last_run = run
                checkpoint.error = ""
                checkpoint.save(update_fields=["last_run", "error"])
                try:
                    created, skipped = process_message(
                        run, checkpoint, mailbox.fetch(uid), client
                    )
                    if not run.dry_run and not checkpoint.completed_at:
                        checkpoint.completed_at = timezone.now()
                        checkpoint.error = ""
                        checkpoint.save()
                    run.reports_created += created
                    run.reports_skipped += skipped
                    run.messages_processed += 1
                except (
                    SourceError,
                    requests.RequestException,
                    OSError,
                    ValueError,
                    TypeError,
                    LookupError,
                    ValidationError,
                    PdfReadError,
                ) as error:
                    # Message boundaries deliberately isolate failures. Persist a
                    # failed checkpoint and failed run, then retry next sync.
                    run.messages_failed += 1
                    checkpoint.error = f"{run.stage}: {safe_error(error)}"[:255]
                    checkpoint.save(update_fields=["error"])
                progress(run, "Checking next message")
        run.status = (
            IngestionRun.Status.FAILED
            if run.messages_failed
            else IngestionRun.Status.SUCCEEDED
        )
        run.error = (
            f"{run.messages_failed} message(s) failed; see message checkpoints and start another sync to retry."
            if run.messages_failed
            else ""
        )
    except Exception as error:
        run.status = IngestionRun.Status.FAILED
        run.error = safe_error(error)
        raise IngestionError(run.error) from error
    finally:
        run.finished_at = timezone.now()
        run.stage = (
            "Finished" if run.status == IngestionRun.Status.SUCCEEDED else "Failed"
        )
        run.save()
        heartbeat()
    if run.messages_failed:
        raise IngestionError(run.error)
    return run
