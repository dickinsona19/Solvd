from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .auth import create_session, require_session, require_webhook
from .config import settings
from .db import initialize_database
from .ingest import start_poller, stop_poller
from .inbox import (
    account_bundle,
    ingest_message,
    live_inbox,
    request_analysis,
    resume_queued,
    seed_fixture,
)

logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=500)


class Sender(BaseModel):
    name: str = ""
    email: str = Field(min_length=3, max_length=320)


class EmailEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(min_length=1, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)
    sender: Sender = Field(alias="from")
    to: str = Field(default="", max_length=320)
    subject: str = Field(default="", max_length=2000)
    body_text: str = Field(min_length=1, max_length=50000)
    received_at: datetime
    labels: list[str] = Field(default_factory=lambda: ["INBOX", "UNREAD"])
    headers: dict[str, str] = Field(default_factory=dict)
    member_id: str | None = None

    def as_message(self) -> dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id or self.id,
            "from": self.sender.model_dump(),
            "to": self.to,
            "subject": self.subject,
            "body_text": self.body_text,
            "received_at": self.received_at.isoformat(),
            "labels": self.labels,
            "headers": self.headers,
            "member_id": self.member_id,
        }


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate()
    initialize_database()
    if settings.email_source == "fixture":
        changed = seed_fixture(settings.account_id)
        logger.info(
            "Email source is temporary JSON (%s changed message(s), AI mode: %s)",
            changed,
            settings.fixture_ai_mode,
        )
    resume_queued()
    if settings.email_source == "imap":
        start_poller()
        logger.info("Email source is IMAP polling")
    elif settings.email_source == "webhook":
        logger.info("Email source is authenticated webhooks")
    yield
    stop_poller()


app = FastAPI(title="SOLVD Smart Inbox API", version="1.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/healthz")
def health() -> dict:
    return {
        "status": "ok",
        "emailSource": settings.email_source,
        "imap": "configured" if settings.imap_enabled else "not-configured",
        "fixtureAiMode": settings.fixture_ai_mode if settings.email_source == "fixture" else None,
    }


@app.post("/api/v1/session")
def login(credentials: LoginRequest) -> dict:
    session = create_session(credentials.username, credentials.password)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return session


@app.get("/api/v1/account")
def get_account(session: dict = Depends(require_session)) -> dict:
    return account_bundle(session["account"])


@app.get("/api/v1/inbox")
def get_inbox(session: dict = Depends(require_session)) -> dict:
    return live_inbox(session["account"])


@app.post("/api/v1/inbox/{message_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze(message_id: str, session: dict = Depends(require_session)) -> dict:
    try:
        state = request_analysis(session["account"], message_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found") from error
    return {"id": message_id, "status": state}


@app.post("/api/v1/webhooks/email", status_code=status.HTTP_202_ACCEPTED)
def email_webhook(event: EmailEvent, _: None = Depends(require_webhook)) -> dict:
    record, changed = ingest_message(settings.account_id, event.as_message())
    return {
        "id": record.message_id,
        "status": record.status,
        "accepted": changed,
        "reason": record.decision_reason,
    }
