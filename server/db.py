from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class TenantAccount(Base):
    __tablename__ = "tenant_account"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    data_source: Mapped[str] = mapped_column(String(32), default="fixture")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    webhook_secret_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class UserIdentity(Base):
    __tablename__ = "user_identity"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120))
    username_normalized: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_account.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), default="owner")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class EmailRecord(Base):
    __tablename__ = "inbox_email"
    __table_args__ = (
        UniqueConstraint("account_id", "message_id", name="uq_inbox_account_message"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(80), index=True)
    message_id: Mapped[str] = mapped_column(String(255))
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    from_name: Mapped[str] = mapped_column(String(255), default="")
    from_email: Mapped[str] = mapped_column(String(320), index=True)
    to_email: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    member_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), index=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def as_message(self) -> dict:
        received = self.received_at
        if received.tzinfo is None:
            received = received.replace(tzinfo=UTC)
        return {
            "id": self.message_id,
            "thread_id": self.thread_id,
            "from": {"name": self.from_name or self.from_email, "email": self.from_email},
            "to": self.to_email,
            "subject": self.subject,
            "body_text": self.body_text,
            "received_at": received.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "labels": self.labels,
            "member_id": self.member_id,
        }


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database() -> None:
    Base.metadata.create_all(engine)
