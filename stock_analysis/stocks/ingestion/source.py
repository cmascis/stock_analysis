"""Read-only Gmail access and bounded, TLS-verified BofA requests."""

import hashlib
import imaplib
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from pypdf import PdfReader


class SourceError(Exception):
    pass


def validate_configuration():
    if not settings.BOFA_GMAIL_EMAIL or not settings.BOFA_GMAIL_APP_PASSWORD:
        raise SourceError(
            "Set GMAIL_EMAIL and GMAIL_APP_PASSWORD in the worker environment."
        )
    if not settings.BOFA_GMAIL_LABEL:
        raise SourceError("GMAIL_LABEL must not be empty.")
    if settings.BOFA_REQUEST_DELAY < 0:
        raise SourceError("BOFA_REQUEST_DELAY must be nonnegative.")


@dataclass
class MailMessage:
    source: bytes
    received_at: datetime

    def report_link_and_date(self):
        message = BytesParser(policy=policy.default).parsebytes(self.source)
        html = []
        dates = []
        for part in message.walk():
            if part.get("Date"):
                try:
                    date = parsedate_to_datetime(str(part["Date"]))
                except ValueError, TypeError:
                    date = None
                if date and date.tzinfo:
                    dates.append(date)
            if (
                part.get_content_type() == "text/html"
                and part.get_content_disposition() != "attachment"
            ):
                html.append(part.get_content(errors="strict"))
        soup = BeautifulSoup("\n".join(html), "html.parser")
        for link in soup.find_all("a", href=True):
            if (
                "FULL REPORT"
                in " ".join(link.get_text(" ", strip=True).split()).upper()
            ):
                return link["href"], min(dates) if dates else self.received_at
        raise SourceError("Email has no FULL REPORT link in its HTML.")


class GmailMailbox:
    def __init__(self, mailbox):
        self.mailbox = mailbox

    def message_ids(self, limit):
        label = (
            '"'
            + settings.BOFA_GMAIL_LABEL.replace("\\", "\\\\").replace('"', '\\"')
            + '"'
        )
        status, _ = self.mailbox.select(label, readonly=True)
        if status != "OK":
            raise SourceError(
                "Cannot open the configured Gmail label; check IMAP visibility."
            )
        _, validity = self.mailbox.response("UIDVALIDITY")
        if not validity or not validity[0]:
            raise SourceError(
                "Gmail did not return UIDVALIDITY; refusing unstable message identities."
            )
        self.validity = validity[0].decode("ascii")
        status, data = self.mailbox.uid("search", None, "ALL")
        if status != "OK":
            raise SourceError("Cannot search the Gmail label.")
        uids = sorted(data[0].split(), key=int)
        return uids[-limit:] if limit else uids

    def source_key(self, uid):
        identity = [
            settings.BOFA_GMAIL_EMAIL.lower(),
            settings.BOFA_GMAIL_LABEL,
            self.validity,
            uid.decode("ascii"),
        ]
        return hashlib.sha256("\0".join(identity).encode()).hexdigest()

    def fetch(self, uid):
        status, data = self.mailbox.uid("fetch", uid, "(INTERNALDATE BODY.PEEK[])")
        if status != "OK":
            raise SourceError("Cannot fetch Gmail message.")
        literals = [item for item in data if isinstance(item, tuple)]
        if len(literals) != 1 or not isinstance(literals[0][1], bytes):
            raise SourceError("Gmail returned incomplete email content.")
        metadata = b" ".join(
            item[0] if isinstance(item, tuple) else item
            for item in data
            if isinstance(item, (tuple, bytes))
        )
        received = imaplib.Internaldate2tuple(metadata)
        if received is None:
            raise SourceError("Gmail message has no received date.")
        return MailMessage(
            literals[0][1], datetime.fromtimestamp(time.mktime(received), UTC)
        )


@contextmanager
def open_mailbox():
    validate_configuration()
    try:
        with imaplib.IMAP4_SSL(
            "imap.gmail.com",
            port=993,
            ssl_context=ssl.create_default_context(),
            timeout=30,
        ) as mailbox:
            mailbox.login(settings.BOFA_GMAIL_EMAIL, settings.BOFA_GMAIL_APP_PASSWORD)
            yield GmailMailbox(mailbox)
    except imaplib.IMAP4.error as error:
        raise SourceError(
            "Gmail IMAP failed; check the app password and label configuration."
        ) from error


def validate_url(url):
    parts = urlsplit(url)
    # Existing BofA emails use an HTTP research1 redirect link. Upgrade this
    # specific legacy entry point before sending any network request.
    if (
        parts.scheme == "http"
        and parts.hostname == "research1.ml.com"
        and parts.path == "/C"
        and parts.port in (None, 80)
        and not parts.username
        and not parts.password
    ):
        parts = parts._replace(scheme="https", netloc="research1.ml.com")
        url = urlunsplit(parts)
    if (
        parts.scheme != "https"
        or parts.hostname not in settings.BOFA_ALLOWED_HOSTS
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
    ):
        raise SourceError("Report URL is outside the configured HTTPS BofA hosts.")
    return url


def accessible_url(url):
    parts = urlsplit(validate_url(url))
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in {"ps", "pv"}
    ]
    query.extend([("ps", "true"), ("pv", "validated")])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class BofAClient:
    def __enter__(self):
        self.session = requests.Session()
        return self

    def __exit__(self, *args):
        self.session.close()

    def request(self, url, *, data=None):
        method = "POST" if data is not None else "GET"
        for _ in range(10):
            url = validate_url(url)
            time.sleep(settings.BOFA_REQUEST_DELAY)
            response = self.session.request(
                method, url, data=data, allow_redirects=False, timeout=(15, 60)
            )
            response.raise_for_status()
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                if response.status_code in (301, 302, 303):
                    method, data = "GET", None
                continue
            return response
        raise SourceError("Report exceeded the redirect limit.")

    def download_pdf(self, url):
        response = self.request(url)
        if not response.content.lstrip().startswith(b"%PDF-"):
            soup = BeautifulSoup(response.text, "html.parser")
            proceed = soup.find("input", {"name": "Proceed"})
            if proceed is None:
                raise SourceError("Report link did not return a PDF or a Proceed form.")
            data = {"Proceed": "Proceed"}
            for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
                field = soup.find("input", {"name": name})
                if field is None or not field.has_attr("value"):
                    raise SourceError("BofA Proceed form is incomplete.")
                data[name] = field["value"]
            response = self.request(response.url, data=data)
        if not response.content.lstrip().startswith(b"%PDF-"):
            raise SourceError("Report download returned non-PDF content.")
        return response.content

    def html(self, url):
        response = self.request(accessible_url(url))
        if "This publication is not available." in response.text:
            raise SourceError("BofA publication is unavailable; it will be retried.")
        return response.text


def accessible_link_from_pdf(content):
    reader = PdfReader(BytesIO(content))
    if not reader.pages:
        raise SourceError("Report PDF has no pages.")
    annotations = reader.pages[0].get("/Annots", [])
    if hasattr(annotations, "get_object"):
        annotations = annotations.get_object()
    for annotation in reversed(annotations):
        action = annotation.get_object().get("/A")
        if not action:
            continue
        uri = action.get_object().get("/URI", "")
        parts = urlsplit(uri)
        if parts.hostname in settings.BOFA_ALLOWED_HOSTS and (
            "access" in parts.path.lower() or parts.path == "/r"
        ):
            return validate_url(uri)
    raise SourceError("Report PDF has no recognized accessible-version link.")
