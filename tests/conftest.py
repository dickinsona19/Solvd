from __future__ import annotations

import os
import uuid
from pathlib import Path

TEST_DATABASE = Path(f".pytest-{uuid.uuid4().hex}.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"


def pytest_sessionfinish() -> None:
    from server.db import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)
