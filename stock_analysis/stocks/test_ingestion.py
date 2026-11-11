import hashlib
import imaplib
import json
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from email.message import EmailMessage
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from stocks.ingestion import runner
from stocks.ingestion.parsers import extract_company_data, extract_subpage_links
from stocks.ingestion.schedule import daily_schedule, daily_sync_due
from stocks.ingestion.source import (
    BofAClient,
    GmailMailbox,
    MailMessage,
    SourceError,
    accessible_link_from_pdf,
    accessible_url,
    open_mailbox,
    validate_url,
)
from stocks.models import (
    DailyReport,
    IngestionMessage,
    IngestionRun,
    IngestionWorker,
    Stock,
)
from stocks.report_import import import_record, prepare_record

MAIN_HTML = """<section class="portlet" id="portlet_HtmlComponent_WAR_RLWebReportsportlet_INSTANCE_1">
<p><a href="https://rsch.baml.com/r?q=company">Example Company</a><span>| BUY | ABC US | Mkt Cap:USD 1 bn</span></p>
<p>Company update.</p></section>"""
COMPANY_HTML = """<input id="analystTeamName" value="Example%20Team"><input id="reportSubTitle" value="Company%20update">
<ul class="key-takeaways-list"><li>Growing revenue</li></ul>
<div id="_DataScroller_WAR_RLWebReportsportlet_INSTANCE_1">ABC US</div>
<div><h2>Financials</h2><div>Price</div><div>100</div><div>USD</div>
<div>Price Objective</div><div>120</div><div>USD</div><div>Upside</div><div>20%</div>
<div>Average Daily Value</div><div>2</div><div>USD(mn)</div>
<div>2027E EPS</div><div>4.5</div><div>USD</div></div>"""


def record(**changes):
    return {
        "Ticker": "ABC US",
        "Company": "Example Company",
        "Timestamp": "2026-11-10_12-00",
        "Link": "https://rsch.baml.com/access?q=company",
        "Price": 100,
        "Rating": "BUY",
        "Currency": "USD",
        "Key_Takeaways": ["Growing revenue"],
        "2027E_EPS": "4.5",
        **changes,
    }


def mail():
    message = EmailMessage()
    message["Date"] = "Tue, 10 Nov 2026 12:00:00 +0000"
    message.set_content("Report")
    message.add_alternative(
        '<a href="https://rsch.baml.com/r?q=digest"><span>FULL REPORT</span></a>',
        subtype="html",
    )
    return MailMessage(message.as_bytes(), timezone.now())


def pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    annotation = DictionaryObject(
        {
            NameObject("/A"): DictionaryObject(
                {
                    NameObject("/URI"): TextStringObject(
                        "https://rsch.baml.com/access?q=digest"
                    )
                }
            )
        }
    )
    page[NameObject("/Annots")] = writer._add_object(ArrayObject([annotation]))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class ScheduleTests(SimpleTestCase):
    def setUp(self):
        self.slots, self.zone = daily_schedule("11:00,17:00", "America/New_York")

    def test_only_due_after_daily_slots_and_once_per_slot(self):
        cases = [
            ("2026-11-12T15:59:00+00:00", None, False),
            ("2026-11-12T16:00:00+00:00", None, True),
            ("2026-11-12T21:59:00+00:00", "2026-11-12T16:00:00+00:00", False),
            ("2026-11-12T22:00:00+00:00", "2026-11-12T16:00:00+00:00", True),
            ("2026-11-12T23:00:00+00:00", "2026-11-12T22:00:00+00:00", False),
            ("2026-11-13T05:05:00+00:00", "2026-11-12T22:00:00+00:00", False),
            ("2026-11-13T16:00:00+00:00", "2026-11-12T22:00:00+00:00", True),
        ]
        for now, last, expected in cases:
            with self.subTest(now=now, last=last):
                self.assertEqual(
                    daily_sync_due(
                        datetime.fromisoformat(now),
                        datetime.fromisoformat(last) if last else None,
                        self.slots,
                        self.zone,
                    ),
                    expected,
                )

    def test_eastern_wall_clock_tracks_daylight_saving(self):
        for date, utc_hour in (
            ("2026-03-07", 16),
            ("2026-03-08", 15),
            ("2026-10-31", 15),
            ("2026-11-01", 16),
        ):
            with self.subTest(date=date):
                before = datetime.fromisoformat(
                    f"{date}T{utc_hour - 1:02d}:59:00+00:00"
                )
                at = datetime.fromisoformat(f"{date}T{utc_hour:02d}:00:00+00:00")
                self.assertFalse(daily_sync_due(before, None, self.slots, self.zone))
                self.assertTrue(daily_sync_due(at, None, self.slots, self.zone))

    def test_invalid_schedule_fails_before_worker_starts(self):
        for kwargs in ({"times": "25:00"}, {"times": ""}, {"timezone": "Invalid/Zone"}):
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaisesRegex(CommandError, "Invalid daily schedule"),
            ):
                call_command("ingestion_worker", once=True, **kwargs)


class ParsingTests(SimpleTestCase):
    def test_extract_clean_and_prepare_complete_record(self):
        _, _, stock = extract_subpage_links(MAIN_HTML)[0]
        stock["Timestamp"] = "2026-11-10_12-00"
        data = runner.clean(extract_company_data(COMPANY_HTML, stock))
        self.assertEqual(data["Price"], 100)
        self.assertEqual(data["Price_Objective"], 120)
        self.assertEqual(data["Upside"], 0.2)
        self.assertEqual(data["Average_Daily_Value"], 2000000)
        self.assertEqual(data["Market_Cap"], 1000000000)
        self.assertEqual(data["2027E_EPS"], 4.5)
        self.assertEqual(data["Analyst_Team"], "Example Team")
        self.assertTrue(prepare_record(data).fingerprint)

    def test_company_login_page_fails_instead_of_importing_summary_only(self):
        with self.assertRaisesRegex(ValueError, "no matching financials"):
            extract_company_data("<html>Sign in</html>", {"Ticker": "ABC US"})

    def test_invalid_numeric_value_fails_instead_of_silently_omitting_metric(self):
        with self.assertRaisesRegex(ValueError, "Invalid numeric"):
            extract_company_data(
                COMPANY_HTML.replace("<div>100</div>", "<div>oops</div>"),
                {"Ticker": "ABC US"},
            )

    def test_ticker_with_period_and_ascii_cleaning(self):
        self.assertEqual(
            extract_subpage_links(MAIN_HTML.replace("ABC US", "BRK.B US"))[0][2][
                "Ticker"
            ],
            "BRK.B US",
        )
        self.assertEqual(runner.clean({"Company": "Caf\u00e9"}), {"Company": "Cafe"})

    def test_missing_timestamp_nonfinite_and_bad_arrays_are_rejected(self):
        for changes in (
            {"Timestamp": None},
            {"Price": "NaN"},
            {"Price": "Infinity"},
            {"Price": "N/A"},
            {"Key_Takeaways": "bad"},
            {"Raw_Text": [1]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_record(record(**changes))

    def test_eps_priority_and_float_precision(self):
        prepared = prepare_record(
            record(
                **{"327_EPS": 1, "2027_EPS": 2, "2027E_EPS": 3, "Upside": 0.123456789}
            )
        )
        self.assertEqual(prepared.eps, [(2027, Decimal(3))])
        self.assertEqual(prepared.fields["upside"], Decimal("0.123457"))

    def test_email_original_date_over_received_date_and_nested_html(self):
        link, date = mail().report_link_and_date()
        self.assertIn("q=digest", link)
        self.assertEqual(date.strftime("%Y-%m-%d_%H-%M"), "2026-11-10_12-00")
        wrapper = EmailMessage()
        from email import policy
        from email.parser import BytesParser

        wrapper.set_content("Forwarded report")
        wrapper.add_attachment(
            BytesParser(policy=policy.default).parsebytes(mail().source)
        )
        self.assertEqual(
            MailMessage(wrapper.as_bytes(), timezone.now()).report_link_and_date(),
            (link, date),
        )

    def test_pdf_accessible_link(self):
        self.assertEqual(
            accessible_link_from_pdf(pdf()), "https://rsch.baml.com/access?q=digest"
        )

    def test_url_validation_and_query_parameters(self):
        self.assertEqual(
            validate_url("http://research1.ml.com/C?token=example"),
            "https://research1.ml.com/C?token=example",
        )
        for url in (
            "http://rsch.baml.com/access",
            "https://example.com",
            "https://rsch.baml.com.evil.com",
            "https://user@rsch.baml.com/access",
            "https://rsch.baml.com:444/access",
        ):
            with self.subTest(url=url), self.assertRaises(SourceError):
                validate_url(url)
        self.assertEqual(
            accessible_url("https://rsch.baml.com/access?q=a&ps=false"),
            "https://rsch.baml.com/access?q=a&ps=true&pv=validated",
        )


@override_settings(
    BOFA_REQUEST_DELAY=0,
    BOFA_GMAIL_EMAIL="reports@gmail.com",
    BOFA_GMAIL_APP_PASSWORD="test",
    BOFA_GMAIL_LABEL="BofA Analysis",
)
class SourceTests(SimpleTestCase):
    @patch("stocks.ingestion.source.imaplib.IMAP4_SSL")
    def test_tls_and_context_cleanup(self, connection_mock):
        import ssl

        with open_mailbox():
            pass
        self.assertTrue(connection_mock.call_args.kwargs["ssl_context"].check_hostname)
        self.assertEqual(
            connection_mock.call_args.kwargs["ssl_context"].verify_mode,
            ssl.CERT_REQUIRED,
        )
        connection_mock.return_value.__enter__.return_value.login.assert_called_once_with(
            "reports@gmail.com", "test"
        )
        connection_mock.return_value.__exit__.assert_called_once()

    @patch("stocks.ingestion.source.imaplib.IMAP4_SSL")
    def test_login_failure_and_missing_credentials(self, connection_mock):
        connection_mock.return_value.__enter__.return_value.login.side_effect = (
            imaplib.IMAP4.error("bad")
        )
        with self.assertRaises(SourceError), open_mailbox():
            self.fail("Must not yield after failed login")
        with (
            override_settings(BOFA_GMAIL_APP_PASSWORD=""),
            self.assertRaises(SourceError),
            open_mailbox(),
        ):
            self.fail("Must require credentials")

    def test_uidvalidity_readonly_and_body_peek(self):
        raw = Mock()
        raw.select.return_value = ("OK", [b"2"])
        raw.response.return_value = ("UIDVALIDITY", [b"123"])
        raw.uid.side_effect = [
            ("OK", [b"1 20 3"]),
            (
                "OK",
                [
                    (b"1 (BODY[] {1}", mail().source),
                    b' INTERNALDATE "10-Nov-2026 12:00:00 +0000")',
                ],
            ),
        ]
        mailbox = GmailMailbox(raw)
        self.assertEqual(mailbox.message_ids(1), [b"20"])
        raw.select.assert_called_once_with('"BofA Analysis"', readonly=True)
        old_key = mailbox.source_key(b"20")
        mailbox.validity = "124"
        self.assertNotEqual(old_key, mailbox.source_key(b"20"))
        self.assertTrue(mailbox.fetch(b"20").source)
        self.assertEqual(
            raw.uid.call_args.args, ("fetch", b"20", "(INTERNALDATE BODY.PEEK[])")
        )

    def test_missing_uidvalidity_is_explicit_error(self):
        raw = Mock()
        raw.select.return_value = ("OK", [])
        raw.response.return_value = (None, [None])
        with self.assertRaises(SourceError):
            GmailMailbox(raw).message_ids(0)

    @patch("stocks.ingestion.source.requests.Session")
    def test_redirect_to_unknown_host_is_not_followed(self, session):
        response = Mock(
            is_redirect=True,
            status_code=302,
            headers={"Location": "http://127.0.0.1/private"},
        )
        session.return_value.request.return_value = response
        with BofAClient() as client, self.assertRaises(SourceError):
            client.request("https://rsch.baml.com/r?q=test")
        self.assertEqual(session.return_value.request.call_count, 1)
        self.assertEqual(
            session.return_value.request.call_args.kwargs["timeout"], (15, 60)
        )

    @patch("stocks.ingestion.source.requests.Session")
    def test_proceed_form_uses_same_session_and_rejects_nonpdf(self, session):
        form = '<input name="Proceed"><input name="__VIEWSTATE" value="v"><input name="__VIEWSTATEGENERATOR" value="g"><input name="__EVENTVALIDATION" value="e">'
        first = Mock(
            is_redirect=False,
            content=b"HTML",
            text=form,
            url="https://rsch.baml.com/r?q=test",
        )
        second = Mock(is_redirect=False, content=b"%PDF-test")
        session.return_value.request.side_effect = [first, second]
        with BofAClient() as client:
            self.assertEqual(client.download_pdf(first.url), b"%PDF-test")
        self.assertEqual(session.return_value.request.call_args.args[0], "POST")
        session.return_value.request.side_effect = None
        session.return_value.request.return_value = Mock(
            is_redirect=False, content=b"HTML", text="<p>Login</p>"
        )
        with BofAClient() as client, self.assertRaises(SourceError):
            client.download_pdf(first.url)


class ImportTests(TestCase):
    def test_manual_import_preserves_timestamp_dedup_and_existing_values(self):
        self.assertTrue(import_record(prepare_record(record())))
        self.assertFalse(import_record(prepare_record(record(Price=200))))
        self.assertEqual(DailyReport.objects.get().price, 100)

    def test_forwarded_duplicate_and_legacy_duplicate_are_skipped(self):
        import_record(prepare_record(record()), deduplicate_content=True)
        self.assertFalse(
            import_record(
                prepare_record(record(Timestamp="2026-11-11_12-00")),
                deduplicate_content=True,
            )
        )
        DailyReport.objects.update(ingestion_fingerprint="")
        DailyReport.objects.update(link="https://rsch.baml.com/r?ps=true&q=company")
        self.assertFalse(
            import_record(
                prepare_record(record(Timestamp="2026-11-12_12-00")),
                deduplicate_content=True,
            )
        )
        self.assertTrue(
            import_record(
                prepare_record(record(Timestamp="2026-11-12_12-00", Price=101)),
                deduplicate_content=True,
            )
        )

    def test_source_file_dry_run_and_invalid_records_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reports.json"
            path.write_text(json.dumps([record()]))
            call_command("import_reports", source=path, dry_run=True, stdout=StringIO())
            self.assertEqual(Stock.objects.count(), 0)
            path.write_text(json.dumps([record(), record(Timestamp=None)]))
            with self.assertRaises(CommandError):
                call_command(
                    "import_reports", source=path, stdout=StringIO(), stderr=StringIO()
                )
            self.assertEqual(DailyReport.objects.count(), 1)


class RunnerTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(
            BOFA_INGESTION_DIR=Path(self.temp.name)
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.mailbox_patch = patch.object(runner, "open_mailbox")
        self.mailbox = self.mailbox_patch.start().return_value.__enter__.return_value
        self.addCleanup(self.mailbox_patch.stop)
        self.mailbox.message_ids.return_value = [b"1"]
        self.mailbox.source_key.side_effect = lambda uid: hashlib.sha256(
            uid
        ).hexdigest()
        self.mailbox.fetch.return_value = mail()
        self.client_patch = patch.object(runner, "BofAClient")
        self.client = self.client_patch.start().return_value.__enter__.return_value
        self.addCleanup(self.client_patch.stop)
        self.pdf = pdf()
        self.client.download_pdf.return_value = self.pdf
        self.client.html.side_effect = lambda url: (
            MAIN_HTML if "q=digest" in url else COMPANY_HTML
        )

    def run_sync(self, **kwargs):
        run, _ = runner.enqueue_run(**kwargs)
        runner.execute_run(run)
        return run

    def test_full_pipeline_persists_and_second_run_does_not_fetch_mail(self):
        run = self.run_sync()
        self.assertEqual(run.reports_created, 1)
        self.assertEqual(
            DailyReport.objects.get().as_of_timestamp.strftime("%Y-%m-%d"), "2026-11-10"
        )
        self.assertTrue(IngestionMessage.objects.get().completed_at)
        self.assertTrue(list(Path(self.temp.name).rglob("reports.json")))
        self.run_sync()
        self.mailbox.fetch.assert_called_once()
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_duplicate_pdf_from_new_uid_does_not_reextract(self):
        self.run_sync()
        self.mailbox.message_ids.return_value = [b"2"]
        self.run_sync()
        self.assertEqual(self.client.html.call_count, 2)
        self.assertEqual(
            IngestionMessage.objects.filter(completed_at__isnull=False).count(), 2
        )
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_failed_company_retries_without_partial_import_or_json(self):
        self.client.html.side_effect = [
            MAIN_HTML,
            requests.Timeout("https://secret-signed-url"),
        ]
        with self.assertRaises(runner.IngestionError):
            self.run_sync()
        self.assertEqual(DailyReport.objects.count(), 0)
        self.assertFalse(list(Path(self.temp.name).rglob("reports.json")))
        checkpoint = IngestionMessage.objects.get()
        self.assertIsNone(checkpoint.completed_at)
        self.assertNotIn("secret", checkpoint.error)
        self.client.html.side_effect = lambda url: COMPANY_HTML
        run = self.run_sync()
        self.assertEqual(run.status, IngestionRun.Status.SUCCEEDED)
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_dry_run_does_not_import_or_complete_then_real_run_succeeds(self):
        self.run_sync(dry_run=True)
        self.assertEqual(DailyReport.objects.count(), 0)
        self.assertIsNone(IngestionMessage.objects.get().completed_at)
        self.run_sync()
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_import_failure_rolls_back_entire_digest_and_checkpoint(self):
        self.client.html.side_effect = lambda url: (
            MAIN_HTML
            + MAIN_HTML.replace("q=company", "q=other").replace("ABC US", "XYZ US")
            if "q=digest" in url
            else COMPANY_HTML.replace("ABC US", "XYZ US")
            if "q=other" in url
            else COMPANY_HTML
        )
        real_import = runner.import_record
        count = 0

        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError("Second report failed")
            return real_import(*args, **kwargs)

        with (
            patch.object(runner, "import_record", side_effect=fail_second),
            self.assertRaises(runner.IngestionError),
        ):
            self.run_sync()
        self.assertEqual(DailyReport.objects.count(), 0)
        self.assertIsNone(IngestionMessage.objects.get().completed_at)

    def test_queue_deduplication_and_interrupted_run_recovery(self):
        first, created = runner.enqueue_run()
        second, created_again = runner.enqueue_run()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IngestionRun.objects.create()
        first.status = IngestionRun.Status.RUNNING
        first.save()
        runner.recover_interrupted_runs()
        first.refresh_from_db()
        self.assertEqual(first.status, IngestionRun.Status.FAILED)
        self.assertIsNotNone(first.finished_at)

    def test_worker_once_handles_queued_run_and_does_not_duplicate_schedule(self):
        runner.enqueue_run()
        call_command("ingestion_worker", once=True, interval=900, stdout=StringIO())
        self.assertEqual(DailyReport.objects.count(), 1)
        call_command("ingestion_worker", once=True, interval=900, stdout=StringIO())
        self.assertEqual(IngestionRun.objects.count(), 1)

    def test_daily_worker_runs_at_due_time_once_and_manual_queue_runs_before_due(self):
        now = datetime(2026, 11, 12, 16, 0, tzinfo=UTC)
        with patch(
            "stocks.management.commands.ingestion_worker.timezone.now", return_value=now
        ):
            call_command(
                "ingestion_worker",
                once=True,
                times="11:00,17:00",
                timezone="America/New_York",
                stdout=StringIO(),
            )
            # The model captured its default clock before this patch.
            IngestionRun.objects.update(queued_at=now)
            call_command(
                "ingestion_worker",
                once=True,
                times="11:00,17:00",
                timezone="America/New_York",
                stdout=StringIO(),
            )
        self.assertEqual(IngestionRun.objects.count(), 1)
        self.assertEqual(DailyReport.objects.count(), 1)
        self.client.html.reset_mock()
        runner.enqueue_run()
        with patch(
            "stocks.management.commands.ingestion_worker.timezone.now",
            return_value=datetime(2026, 11, 13, 14, tzinfo=UTC),
        ):
            call_command(
                "ingestion_worker",
                once=True,
                times="11:00,17:00",
                timezone="America/New_York",
                stdout=StringIO(),
            )
        self.assertEqual(IngestionRun.objects.count(), 2)
        self.assertEqual(
            IngestionRun.objects.first().status, IngestionRun.Status.SUCCEEDED
        )

    def test_missing_configuration_fails_run_visibly(self):
        self.mailbox_patch.stop()
        with (
            override_settings(BOFA_GMAIL_EMAIL="", BOFA_GMAIL_APP_PASSWORD=""),
            self.assertRaisesRegex(CommandError, "GMAIL_EMAIL"),
        ):
            call_command("sync_bofa_reports", stdout=StringIO())
        self.assertEqual(IngestionRun.objects.get().status, IngestionRun.Status.FAILED)


class AdminTests(TestCase):
    def setUp(self):
        self.url = reverse("admin:stocks_ingestionrun_sync")
        self.list_url = reverse("admin:stocks_ingestionrun_changelist")
        self.staff = get_user_model().objects.create_user(
            username="staff", is_staff=True
        )

    def test_anonymous_regular_user_and_staff_without_permission_cannot_queue(self):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        user = get_user_model().objects.create_user(username="regular")
        self.client.force_login(user)
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertEqual(IngestionRun.objects.count(), 0)

    def test_authorized_staff_csrf_post_only_queue_and_run_history(self):
        self.staff.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["add_ingestionrun", "view_ingestionrun"]
            )
        )
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertContains(self.client.get(self.list_url), "Worker is offline")
        IngestionWorker.objects.create(heartbeat_at=timezone.now())
        self.assertContains(self.client.get(self.list_url), "Worker is active")
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.client.post(self.url)
        self.assertEqual(IngestionRun.objects.count(), 1)
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(csrf_client.post(self.url).status_code, 403)
        self.assertContains(
            self.client.get(
                reverse(
                    "admin:stocks_ingestionrun_change",
                    args=[IngestionRun.objects.get().pk],
                )
            ),
            "Queued",
        )


class LockTests(TransactionTestCase):
    def test_second_database_session_cannot_acquire_worker_lock(self):
        other = connection.copy()
        try:
            with runner.worker_lock(), other.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [runner.LOCK_ID])
                self.assertFalse(cursor.fetchone()[0])
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [runner.LOCK_ID])
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute("SELECT pg_advisory_unlock(%s)", [runner.LOCK_ID])
        finally:
            other.close()
