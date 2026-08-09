from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMAIL_SOURCES = {"auto", "fixture", "imap", "webhook"}
FIXTURE_AI_MODES = {"cache", "process"}


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(
        value.strip().rstrip("/") for value in os.getenv(name, default).split(",") if value.strip()
    )


def _database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("SOLVD_ENV", "development")
    database_url: str = _database_url(os.getenv("DATABASE_URL", "sqlite:///./solvd.db"))
    account_id: str = os.getenv("SOLVD_ACCOUNT_ID", "test")
    account_username: str = os.getenv("SOLVD_ACCOUNT_USERNAME", "test")
    account_password: str = os.getenv("SOLVD_ACCOUNT_PASSWORD", "1234")
    session_secret: str = os.getenv("SOLVD_SESSION_SECRET", "local-development-only")
    webhook_secret: str = os.getenv("SOLVD_EMAIL_WEBHOOK_SECRET", "local-webhook-only")
    admin_secret: str = os.getenv("SOLVD_ADMIN_SECRET", "local-admin-only")
    email_source_setting: str = os.getenv("SOLVD_EMAIL_SOURCE", "auto").strip().lower()
    fixture_ai_setting: str = os.getenv("SOLVD_FIXTURE_AI_MODE", "").strip().lower()
    allowed_origins: tuple[str, ...] = _csv(
        "SOLVD_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    session_hours: int = int(os.getenv("SOLVD_SESSION_HOURS", "12"))
    poll_seconds: int = max(5, int(os.getenv("SOLVD_EMAIL_POLL_SECONDS", "15")))
    lookback_hours: int = max(1, int(os.getenv("SOLVD_EMAIL_LOOKBACK_HOURS", "168")))
    batch_limit: int = min(100, max(1, int(os.getenv("SOLVD_EMAIL_BATCH_LIMIT", "25"))))
    imap_host: str = os.getenv("SOLVD_IMAP_HOST", "")
    imap_port: int = int(os.getenv("SOLVD_IMAP_PORT", "993"))
    imap_username: str = os.getenv("SOLVD_IMAP_USERNAME", "")
    imap_password: str = os.getenv("SOLVD_IMAP_PASSWORD", "")
    imap_mailbox: str = os.getenv("SOLVD_IMAP_MAILBOX", "INBOX")

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def imap_enabled(self) -> bool:
        return bool(self.imap_host and self.imap_username and self.imap_password)

    @property
    def email_source(self) -> str:
        if self.email_source_setting != "auto":
            return self.email_source_setting
        return "imap" if self.imap_enabled else "fixture"

    @property
    def fixture_ai_mode(self) -> str:
        if self.fixture_ai_setting:
            return self.fixture_ai_setting
        return "process" if self.production else "cache"

    @property
    def fixture_path(self) -> Path:
        return ROOT / "accounts" / self.account_id / "messages.json"

    def validate(self) -> None:
        if self.email_source_setting not in EMAIL_SOURCES:
            raise RuntimeError(
                f"SOLVD_EMAIL_SOURCE must be one of: {', '.join(sorted(EMAIL_SOURCES))}"
            )
        if self.fixture_ai_mode not in FIXTURE_AI_MODES:
            raise RuntimeError(
                f"SOLVD_FIXTURE_AI_MODE must be one of: {', '.join(sorted(FIXTURE_AI_MODES))}"
            )
        if self.email_source == "imap" and not self.imap_enabled:
            raise RuntimeError("IMAP email source selected, but mailbox credentials are incomplete")
        if self.email_source == "fixture" and not self.fixture_path.is_file():
            raise RuntimeError(f"Fixture email source not found: {self.fixture_path}")
        if not self.production:
            return
        missing = []
        if not self.account_username:
            missing.append("SOLVD_ACCOUNT_USERNAME")
        if not self.account_password or self.account_password == "1234":
            missing.append("SOLVD_ACCOUNT_PASSWORD")
        if not self.session_secret or self.session_secret == "local-development-only":
            missing.append("SOLVD_SESSION_SECRET")
        if not self.webhook_secret or self.webhook_secret == "local-webhook-only":
            missing.append("SOLVD_EMAIL_WEBHOOK_SECRET")
        if not self.admin_secret or self.admin_secret == "local-admin-only":
            missing.append("SOLVD_ADMIN_SECRET")
        if self.email_source == "fixture" and self.fixture_ai_mode == "process":
            if not os.getenv("OPENAI_API_KEY", "").strip():
                missing.append("OPENAI_API_KEY")
        if missing:
            raise RuntimeError(f"Production secrets are not configured: {', '.join(missing)}")


settings = Settings()
