from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Header, HTTPException, status

from .config import settings


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session(username: str, password: str) -> dict | None:
    valid_user = secrets.compare_digest(username.strip().lower(), settings.account_username.lower())
    valid_password = secrets.compare_digest(password, settings.account_password)
    if not (valid_user and valid_password):
        return None

    expires = int(time.time()) + settings.session_hours * 3600
    payload = {"account": settings.account_id, "label": settings.account_id, "exp": expires}
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(
        hmac.new(settings.session_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    return {"token": f"{body}.{signature}", **payload}


def verify_token(token: str) -> dict:
    try:
        body, supplied = token.split(".", 1)
        expected = _b64encode(
            hmac.new(settings.session_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not secrets.compare_digest(supplied, expected):
            raise ValueError("signature")
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired")
        if payload.get("account") != settings.account_id:
            raise ValueError("account")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired") from error


def require_session(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return verify_token(authorization.removeprefix("Bearer ").strip())


def require_webhook(authorization: str | None = Header(default=None)) -> None:
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not secrets.compare_digest(supplied, settings.webhook_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")
