import time
import uuid

import pytest
from sqlalchemy import delete

from server.auth import create_session, verify_token
from server.db import (
    SessionLocal,
    TenantAccount,
    UserIdentity,
    initialize_database,
)
from server.tenancy import (
    bootstrap_configured_user,
    create_account_user,
    sync_fixture_accounts,
)


def ensure_bootstrap_user():
    initialize_database()
    sync_fixture_accounts()
    bootstrap_configured_user()


def test_session_round_trip():
    ensure_bootstrap_user()
    session = create_session("test", "1234")
    assert session is not None
    payload = verify_token(session["token"])
    assert payload["account"] == "test"
    assert payload["exp"] > time.time()


def test_wrong_password_is_rejected():
    ensure_bootstrap_user()
    assert create_session("test", "wrong") is None


def test_tampered_token_is_rejected():
    ensure_bootstrap_user()
    session = create_session("test", "1234")
    with pytest.raises(Exception):
        verify_token(session["token"] + "x")


def test_password_is_argon2_hashed_in_database():
    ensure_bootstrap_user()
    with SessionLocal() as db:
        user = db.query(UserIdentity).filter_by(username_normalized="test").one()
        assert user.password_hash != "1234"
        assert user.password_hash.startswith("$argon2id$")


def test_each_identity_is_locked_to_one_account():
    ensure_bootstrap_user()
    suffix = uuid.uuid4().hex
    username = f"owner-{suffix}@example.com"
    password = "a-strong-single-account-password"
    other_account_id = f"other-{suffix}"

    with SessionLocal() as db:
        db.add(TenantAccount(id=other_account_id, name="Other Gym", data_source="fixture"))
        db.commit()
    user = create_account_user(other_account_id, username, password, "manager")

    selected = create_session(username, password)
    assert selected["account"] == other_account_id
    assert selected["role"] == "manager"
    payload = verify_token(selected["token"])
    assert payload["account"] == other_account_id

    with SessionLocal() as db:
        db.execute(delete(UserIdentity).where(UserIdentity.id == user["id"]))
        db.execute(delete(TenantAccount).where(TenantAccount.id == other_account_id))
        db.commit()
