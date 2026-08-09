from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from ai.graph import build_graph
from ai.model import DRAFT_MODEL, SORT_MODEL

from .accounts import (
    fixture_messages,
    fixture_results,
    member_id_for_email,
    message_context,
    prompt_context,
    static_account_data,
)
from .config import settings
from .db import EmailRecord, SessionLocal
from .email_policy import decide_email

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inbox-ai")
_active: set[int] = set()
_active_lock = threading.Lock()


def _fingerprint(message: dict) -> str:
    payload = {
        "from": message.get("from"),
        "to": message.get("to"),
        "subject": message.get("subject"),
        "body_text": message.get("body_text"),
        "received_at": message.get("received_at"),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _received(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def ingest_message(account_id: str, message: dict, *, schedule: bool = True) -> tuple[EmailRecord, bool]:
    normalized = dict(message)
    normalized.setdefault("labels", ["INBOX", "UNREAD"])
    normalized.setdefault("headers", {})
    normalized.setdefault("thread_id", normalized["id"])
    normalized.setdefault("to", "")
    normalized.setdefault("member_id", member_id_for_email(account_id, normalized["from"]["email"]))
    digest = _fingerprint(normalized)
    account = static_account_data(account_id)["account"]
    support = {account["gym"].get("support_email", ""), account["owner"].get("email", "")}
    decision = decide_email(normalized, support)

    with SessionLocal() as db:
        record = db.scalar(
            select(EmailRecord).where(
                EmailRecord.account_id == account_id,
                EmailRecord.message_id == normalized["id"],
            )
        )
        changed = record is None or record.fingerprint != digest
        if record is None:
            record = EmailRecord(account_id=account_id, message_id=normalized["id"])
            db.add(record)
        elif not changed:
            return record, False

        record.thread_id = normalized["thread_id"]
        record.from_name = normalized["from"].get("name") or normalized["from"]["email"]
        record.from_email = normalized["from"]["email"].strip().lower()
        record.to_email = normalized.get("to", "")
        record.subject = normalized.get("subject", "")
        record.body_text = normalized.get("body_text", "")[:50000]
        record.received_at = _received(normalized["received_at"])
        record.labels = normalized["labels"]
        record.headers = normalized["headers"]
        record.member_id = normalized.get("member_id")
        record.fingerprint = digest
        record.status = "queued" if decision.should_process else "skipped"
        record.decision_reason = decision.reason
        record.analysis = None
        record.error = None
        record.processed_at = None
        db.commit()
        db.refresh(record)
        record_id = record.id

    if schedule and decision.should_process:
        submit_for_processing(record_id)
    return record, changed


def _apply_cached_fixture_result(record_id: int, entry: dict) -> None:
    with SessionLocal() as db:
        record = db.get(EmailRecord, record_id)
        if not record or record.status != "queued":
            return
        record.status = "ready"
        record.analysis = {
            "sort": entry["sort"],
            "draft": entry["draft"],
            "source": "fixture-cache",
        }
        record.processed_at = datetime.now(timezone.utc)
        db.commit()


def _queue_legacy_fixture_result(record_id: int) -> None:
    """Replace an old cached draft with one real API pass, once."""
    with SessionLocal() as db:
        record = db.get(EmailRecord, record_id)
        if not record or record.status != "ready":
            return
        if (record.analysis or {}).get("source") == "openai":
            return
        record.status = "queued"
        record.analysis = None
        record.processed_at = None
        record.decision_reason = "Temporary JSON message queued for live AI processing"
        db.commit()


def seed_fixture(account_id: str, *, ai_mode: str | None = None) -> int:
    """Load the temporary JSON inbox and return the changed-message count.

    Production defaults to ``process``, which sends actionable fixture messages
    through OpenAI. Local development defaults to ``cache`` for fast, free and
    deterministic startup. Database deduplication prevents repeat calls after a
    successful production pass.
    """
    mode = ai_mode or settings.fixture_ai_mode
    cached = fixture_results(account_id) if mode == "cache" else {}
    changed_count = 0

    for message in fixture_messages(account_id):
        record, changed = ingest_message(account_id, message, schedule=False)
        changed_count += int(changed)
        if changed and record.status == "queued" and message["id"] in cached:
            _apply_cached_fixture_result(record.id, cached[message["id"]])
        elif not changed and mode == "process":
            _queue_legacy_fixture_result(record.id)

    return changed_count


def _process(record_id: int) -> None:
    try:
        with SessionLocal() as db:
            record = db.get(EmailRecord, record_id)
            if not record or record.status not in {"queued", "failed"}:
                return
            record.status = "processing"
            record.attempts += 1
            record.error = None
            db.commit()
            account_id = record.account_id
            message = record.as_message()
            digest = record.fingerprint

        company, gym_info, policy = prompt_context(account_id)
        graph = build_graph(
            company_name=company,
            gym_info=gym_info,
            policy=policy,
        )
        state = graph.invoke({"email": message_context(account_id, message)})
        analysis = {"sort": state["sort"], "draft": state["draft"], "source": "openai"}

        with SessionLocal() as db:
            record = db.get(EmailRecord, record_id)
            if not record or record.fingerprint != digest:
                return
            record.analysis = analysis
            record.status = "ready"
            record.processed_at = datetime.now(timezone.utc)
            record.error = None
            db.commit()
    except Exception as error:  # noqa: BLE001 - keep worker alive and expose a safe retry state
        logger.exception("Smart Inbox processing failed for record %s", record_id)
        with SessionLocal() as db:
            record = db.get(EmailRecord, record_id)
            if record:
                record.status = "failed"
                record.error = str(error).splitlines()[0][:500]
                db.commit()
    finally:
        with _active_lock:
            _active.discard(record_id)


def submit_for_processing(record_id: int) -> bool:
    with _active_lock:
        if record_id in _active:
            return False
        _active.add(record_id)
    _executor.submit(_process, record_id)
    return True


def resume_queued() -> None:
    with SessionLocal() as db:
        ids = db.scalars(
            select(EmailRecord.id).where(EmailRecord.status.in_(("queued", "processing")))
        ).all()
        if ids:
            db.query(EmailRecord).filter(EmailRecord.id.in_(ids)).update(
                {EmailRecord.status: "queued"}, synchronize_session=False
            )
            db.commit()
    for record_id in ids:
        submit_for_processing(record_id)


def request_analysis(account_id: str, message_id: str) -> str:
    with SessionLocal() as db:
        record = db.scalar(
            select(EmailRecord).where(
                EmailRecord.account_id == account_id,
                EmailRecord.message_id == message_id,
            )
        )
        if not record:
            raise KeyError(message_id)
        if record.status == "ready":
            return "ready"
        record.status = "queued"
        record.decision_reason = "Owner requested an AI draft"
        record.error = None
        db.commit()
        record_id = record.id
    submit_for_processing(record_id)
    return "queued"


def live_inbox(account_id: str) -> dict:
    with SessionLocal() as db:
        records = db.scalars(
            select(EmailRecord)
            .where(EmailRecord.account_id == account_id)
            .order_by(EmailRecord.received_at.desc())
        ).all()
        messages = [record.as_message() for record in records]
        results = {}
        for record in records:
            entry = {
                "status": record.status,
                "decision": record.decision_reason,
                "attempts": record.attempts,
            }
            if record.analysis:
                entry.update(
                    {
                        "sort": record.analysis.get("sort"),
                        "draft": record.analysis.get("draft"),
                    }
                )
            if record.processed_at:
                processed = record.processed_at
                if processed.tzinfo is None:
                    processed = processed.replace(tzinfo=timezone.utc)
                entry["processedAt"] = processed.astimezone(timezone.utc).isoformat()
            if record.status == "failed":
                entry["error"] = "Draft generation failed. Retry when the service is available."
            results[record.message_id] = entry
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "models": {"sort": SORT_MODEL, "draft": DRAFT_MODEL},
        "messages": messages,
        "inboxAi": {"results": results},
    }


def account_bundle(account_id: str) -> dict:
    bundle = dict(static_account_data(account_id))
    live = live_inbox(account_id)
    bundle["messages"] = live["messages"]
    bundle["inboxAi"] = live["inboxAi"]
    return bundle
