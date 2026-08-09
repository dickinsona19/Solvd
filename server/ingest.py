from __future__ import annotations

import email
import html
import imaplib
import logging
import re
import threading
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from .config import settings
from .inbox import ingest_message

logger = logging.getLogger(__name__)
_stop = threading.Event()
_thread: threading.Thread | None = None


def _header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError):
        return value


def _plain_body(message: Message) -> str:
    plain, html_body = [], []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        (plain if content_type == "text/plain" else html_body).append(text)
    if plain:
        return "\n".join(plain).strip()
    raw = "\n".join(html_body)
    raw = re.sub(r"<(?:br|/p|/div|/li)\b[^>]*>", "\n", raw, flags=re.I)
    return re.sub(r"<[^>]+>", "", html.unescape(raw)).strip()


def parse_email(raw: bytes, uid: str) -> dict:
    message = email.message_from_bytes(raw)
    from_name, from_email = parseaddr(_header(message.get("From")))
    _, to_email = parseaddr(_header(message.get("To")))
    message_id = (message.get("Message-ID") or f"imap-{uid}").strip("<> ")
    parent = (
        (message.get("In-Reply-To") or message.get("References") or message_id)
        .split()[0]
        .strip("<> ")
    )
    try:
        received_at = parsedate_to_datetime(message.get("Date"))
    except (TypeError, ValueError):
        received_at = datetime.now(UTC)
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    tracked_headers = {
        name: _header(message.get(name))
        for name in ("Auto-Submitted", "Precedence", "List-Id", "X-Auto-Response-Suppress")
        if message.get(name)
    }
    return {
        "id": message_id,
        "thread_id": parent,
        "from": {"name": from_name or from_email, "email": from_email},
        "to": to_email,
        "subject": _header(message.get("Subject")),
        "body_text": _plain_body(message),
        "received_at": received_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "labels": ["INBOX", "UNREAD"],
        "headers": tracked_headers,
    }


def poll_once() -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=settings.lookback_hours)
    since = cutoff.strftime("%d-%b-%Y")
    inserted = 0
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as client:
        client.login(settings.imap_username, settings.imap_password)
        client.select(settings.imap_mailbox, readonly=True)
        status, data = client.uid("search", None, f'(UNSEEN SINCE "{since}")')
        if status != "OK" or not data:
            return 0
        uids = data[0].split()[-settings.batch_limit :]
        for raw_uid in uids:
            uid = raw_uid.decode("ascii")
            status, rows = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            payload = next((row[1] for row in rows if isinstance(row, tuple)), None)
            if not payload:
                continue
            message = parse_email(payload, uid)
            received = datetime.fromisoformat(message["received_at"].replace("Z", "+00:00"))
            if received < cutoff:
                continue
            _, changed = ingest_message(settings.account_id, message)
            inserted += int(changed)
    return inserted


def _loop() -> None:
    while not _stop.is_set():
        try:
            count = poll_once()
            if count:
                logger.info("Ingested %s new or changed email(s)", count)
        except Exception:  # noqa: BLE001 - polling must recover on the next interval
            logger.exception("Mailbox polling failed")
        _stop.wait(settings.poll_seconds)


def start_poller() -> bool:
    global _thread
    if not settings.imap_enabled or (_thread and _thread.is_alive()):
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="imap-poller", daemon=True)
    _thread.start()
    return True


def stop_poller() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
