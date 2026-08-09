import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from server.app import app
from server.db import EmailRecord, SessionLocal, UserIdentity


def test_login_and_authorized_account_bundle():
    with TestClient(app) as client:
        login = client.post("/api/v1/session", json={"username": "test", "password": "1234"})
        assert login.status_code == 200
        token = login.json()["token"]

        account = client.get("/api/v1/account", headers={"Authorization": f"Bearer {token}"})
        assert account.status_code == 200
        assert account.json()["account"]["id"] == "test"
        assert account.json()["inboxAi"]["results"]


def test_webhook_is_authenticated_and_skips_automatic_email():
    message_id = f"test-{uuid.uuid4()}@example.com"
    event = {
        "id": message_id,
        "from": {"name": "Notifier", "email": "no-reply@example.com"},
        "to": "front@northsidebarbell.com",
        "subject": "Automatic response",
        "body_text": "This is an automated notification.",
        "received_at": "2026-08-07T23:00:00Z",
        "labels": ["INBOX", "UNREAD"],
    }
    with TestClient(app) as client:
        assert client.post("/api/v1/webhooks/email", json=event).status_code == 401
        response = client.post(
            "/api/v1/webhooks/email",
            json=event,
            headers={"Authorization": "Bearer local-webhook-only"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "skipped"
        assert response.json()["reason"] == "Automated sender"
    with SessionLocal() as db:
        db.execute(delete(EmailRecord).where(EmailRecord.message_id == message_id))
        db.commit()


def test_admin_can_provision_a_tenant_user():
    username = f"owner-{uuid.uuid4()}@example.com"
    password = "a-secure-provisioned-password"
    payload = {"username": username, "password": password, "role": "manager"}

    with TestClient(app) as client:
        endpoint = "/api/v1/admin/accounts/test/users"
        assert client.post(endpoint, json=payload).status_code == 401
        created = client.post(
            endpoint,
            json=payload,
            headers={"Authorization": "Bearer local-admin-only"},
        )
        assert created.status_code == 201
        login = client.post(
            "/api/v1/session",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200
        assert login.json()["account"] == "test"
        assert login.json()["role"] == "manager"

    with SessionLocal() as db:
        user = db.query(UserIdentity).filter_by(username_normalized=username).one()
        db.delete(user)
        db.commit()
