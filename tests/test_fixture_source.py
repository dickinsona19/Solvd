from types import SimpleNamespace

import pytest

from server import inbox
from server.config import Settings


def test_auto_source_uses_fixture_without_imap_credentials():
    settings = Settings(
        environment="development",
        email_source_setting="auto",
        imap_host="imap.gmail.com",
        imap_username="",
        imap_password="",
    )

    assert settings.email_source == "fixture"
    assert settings.fixture_ai_mode == "cache"


def test_auto_source_switches_to_imap_with_complete_credentials():
    settings = Settings(
        environment="development",
        email_source_setting="auto",
        imap_host="imap.gmail.com",
        imap_username="inbox@example.com",
        imap_password="app-password",
    )

    assert settings.email_source == "imap"


def test_production_fixture_processing_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(
        environment="production",
        account_username="owner",
        account_password="a-strong-password",
        session_secret="session-secret",
        webhook_secret="webhook-secret",
        admin_secret="admin-secret",
        email_source_setting="fixture",
        fixture_ai_setting="process",
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        settings.validate()


def test_fixture_cache_is_local_only_orchestration(monkeypatch):
    message = {"id": "fixture-message"}
    record = SimpleNamespace(id=17, status="queued")
    applied = []

    monkeypatch.setattr(inbox, "fixture_messages", lambda _: [message])
    monkeypatch.setattr(
        inbox,
        "fixture_results",
        lambda _: {"fixture-message": {"sort": {}, "draft": {}}},
    )
    monkeypatch.setattr(inbox, "ingest_message", lambda *_args, **_kwargs: (record, True))
    monkeypatch.setattr(
        inbox,
        "_apply_cached_fixture_result",
        lambda record_id, entry: applied.append((record_id, entry)),
    )

    assert inbox.seed_fixture("test", ai_mode="cache") == 1
    assert applied == [(17, {"sort": {}, "draft": {}})]


def test_fixture_process_mode_requeues_only_legacy_ready_results(monkeypatch):
    message = {"id": "fixture-message"}
    record = SimpleNamespace(id=23, status="ready")
    requeued = []

    monkeypatch.setattr(inbox, "fixture_messages", lambda _: [message])
    monkeypatch.setattr(inbox, "ingest_message", lambda *_args, **_kwargs: (record, False))
    monkeypatch.setattr(inbox, "_queue_legacy_fixture_result", requeued.append)

    assert inbox.seed_fixture("test", ai_mode="process") == 0
    assert requeued == [23]
