from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from .accounts import fixture_account_ids, static_account_data
from .config import settings
from .db import SessionLocal, TenantAccount, UserIdentity
from .passwords import hash_password, password_needs_rehash, verify_password


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def secret_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def sync_fixture_accounts() -> tuple[str, ...]:
    """Register every committed account fixture as an isolated tenant."""
    account_ids = fixture_account_ids()
    with SessionLocal() as db:
        for account_id in account_ids:
            raw = static_account_data(account_id)["account"]
            name = raw.get("gym", {}).get("name") or account_id
            account = db.get(TenantAccount, account_id)
            if account is None:
                account = TenantAccount(id=account_id, name=name, data_source="fixture")
                db.add(account)
            else:
                account.name = name
                account.data_source = "fixture"
        db.commit()
    return account_ids


def bootstrap_configured_user() -> int:
    """Upsert the Render-configured bootstrap owner for one gym account.

    Environment credentials remain useful for first deployment and emergency
    rotation, but normal authentication reads the resulting Argon2 hash from
    Postgres. Other users and accounts are unaffected by later bootstrap edits.
    """
    normalized = normalize_username(settings.account_username)
    with SessionLocal() as db:
        account = db.get(TenantAccount, settings.account_id)
        if account is None or not account.is_active:
            raise RuntimeError(f"Bootstrap account is unavailable: {settings.account_id}")

        user = db.scalar(select(UserIdentity).where(UserIdentity.username_normalized == normalized))
        if user is None:
            user = UserIdentity(
                username=settings.account_username.strip(),
                username_normalized=normalized,
                password_hash=hash_password(settings.account_password),
                account_id=account.id,
                role="owner",
            )
            db.add(user)
            db.flush()
        else:
            user.username = settings.account_username.strip()
            user.is_active = True
            if not verify_password(
                user.password_hash, settings.account_password
            ) or password_needs_rehash(user.password_hash):
                user.password_hash = hash_password(settings.account_password)
            user.account_id = account.id
            user.role = "owner"
        if settings.webhook_secret:
            account.webhook_secret_digest = secret_digest(settings.webhook_secret)
        db.commit()
        return user.id


@dataclass(frozen=True)
class AuthenticatedIdentity:
    user_id: int
    username: str
    account_id: str
    account_name: str
    role: str


def _identity(user: UserIdentity, account: TenantAccount) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        user_id=user.id,
        username=user.username,
        account_id=account.id,
        account_name=account.name,
        role=user.role,
    )


def authenticate_identity(
    username: str,
    password: str,
) -> AuthenticatedIdentity | None:
    normalized = normalize_username(username)
    with SessionLocal() as db:
        user = db.scalar(select(UserIdentity).where(UserIdentity.username_normalized == normalized))
        if not user or not user.is_active:
            verify_password(None, password)
            return None
        if not verify_password(user.password_hash, password):
            return None

        account = db.get(TenantAccount, user.account_id)
        if not account or not account.is_active:
            return None

        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = datetime.now(UTC)
        db.commit()
        return _identity(user, account)


def session_identity(user_id: int, account_id: str) -> AuthenticatedIdentity | None:
    with SessionLocal() as db:
        user = db.get(UserIdentity, user_id)
        if not user or not user.is_active or user.account_id != account_id:
            return None
        account = db.get(TenantAccount, user.account_id)
        if not account or not account.is_active:
            return None
        return _identity(user, account)


def create_account_user(account_id: str, username: str, password: str, role: str) -> dict:
    normalized = normalize_username(username)
    with SessionLocal() as db:
        account = db.get(TenantAccount, account_id)
        if not account or not account.is_active:
            raise KeyError(account_id)
        existing = db.scalar(
            select(UserIdentity).where(UserIdentity.username_normalized == normalized)
        )
        if existing:
            raise ValueError("username")
        user = UserIdentity(
            username=username.strip(),
            username_normalized=normalized,
            password_hash=hash_password(password),
            account_id=account.id,
            role=role,
        )
        db.add(user)
        db.flush()
        db.commit()
        return {"id": user.id, "username": user.username, "account": account.id, "role": role}


def rotate_account_webhook_secret(account_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        account = db.get(TenantAccount, account_id)
        if not account or not account.is_active:
            raise KeyError(account_id)
        account.webhook_secret_digest = secret_digest(token)
        db.commit()
    return token


def verify_account_webhook_secret(account_id: str, supplied: str) -> bool:
    with SessionLocal() as db:
        account = db.get(TenantAccount, account_id)
        expected = account.webhook_secret_digest if account and account.is_active else ""
    return bool(expected) and secrets.compare_digest(secret_digest(supplied), expected)
