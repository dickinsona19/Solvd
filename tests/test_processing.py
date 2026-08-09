import uuid
from datetime import UTC, datetime

from sqlalchemy import delete

from server import inbox
from server.db import EmailRecord, SessionLocal, initialize_database


class FakeGraph:
    def invoke(self, state):
        assert state["email"]["subject"] == "Can I switch classes?"
        return {
            "sort": {
                "category": "schedule",
                "priority": "medium",
                "needs_human": False,
                "confidence": "high",
                "summary": "Member wants to switch classes.",
                "reasoning": "This is a booking change.",
            },
            "draft": {
                "reply": "Yes, I can move that booking.",
                "action": "Move booking in Mindbody",
                "confidence": "high",
            },
        }


def test_actionable_email_calls_graph_once_and_persists_result(monkeypatch):
    initialize_database()
    message_id = f"processing-{uuid.uuid4()}@example.com"
    message = {
        "id": message_id,
        "thread_id": message_id,
        "from": {"name": "Member", "email": "member@example.com"},
        "to": "front@northsidebarbell.com",
        "subject": "Can I switch classes?",
        "body_text": "Can you move me to the 6am class next week?",
        "received_at": datetime.now(UTC).isoformat(),
        "labels": ["INBOX", "UNREAD"],
        "headers": {},
    }
    monkeypatch.setattr(inbox, "build_graph", lambda **_: FakeGraph())

    record, changed = inbox.ingest_message("test", message, schedule=False)
    assert changed
    assert record.status == "queued"
    inbox._process(record.id)

    payload = inbox.live_inbox("test")
    result = payload["inboxAi"]["results"][message_id]
    assert result["status"] == "ready"
    assert result["draft"]["action"] == "Move booking in Mindbody"
    assert "source" not in result

    with SessionLocal() as db:
        stored = db.get(EmailRecord, record.id)
        assert stored.analysis["source"] == "openai"

    same_record, changed = inbox.ingest_message("test", message, schedule=False)
    assert not changed
    assert same_record.id == record.id

    with SessionLocal() as db:
        db.execute(delete(EmailRecord).where(EmailRecord.message_id == message_id))
        db.commit()
