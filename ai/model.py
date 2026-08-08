"""OpenAI chat model wiring for the Smart Inbox agent.

Models are created against OpenAI's **Responses API** (``use_responses_api``),
matching the tradingnewsagent reference. Chat Completions is the older default
in ``ChatOpenAI``; we never want it here.
"""

from __future__ import annotations

import os
import warnings
from functools import lru_cache
from typing import Any

from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load the repo-root .env so OPENAI_API_KEY / SOLVD_*_MODEL resolve before
# graph.py builds models. Does not override real environment variables.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# The Responses API returns richly-typed objects whose union members trigger
# benign PydanticSerializationUnexpectedValue warnings when LangChain
# serializes results. The output itself is correct, so silence this specific
# noise rather than flooding the runner logs.
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings",
    category=UserWarning,
)

# Both passes run on the same model. The 5.6 line has no small tier, so the
# old split of a cheap sorter and an expensive drafter is gone: set
# SOLVD_SORT_MODEL to a nano model if the call volume ever makes that matter.
SORT_MODEL = os.getenv("SOLVD_SORT_MODEL", "gpt-5.6-luna")
DRAFT_MODEL = os.getenv("SOLVD_DRAFT_MODEL", "gpt-5.6-luna")

# Reasoning / GPT-5 family models reject an explicit temperature (only the
# default is accepted), so we must not send one for these.
_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _supports_temperature(model_id: str) -> bool:
    mid = model_id.lower()
    return not any(mid.startswith(prefix) for prefix in _NO_TEMPERATURE_PREFIXES)


@lru_cache(maxsize=8)
def get_llm(model_id: str, *, temperature: float = 0) -> ChatOpenAI:
    """Return a cached chat model routed through the Responses API."""
    kwargs: dict[str, Any] = {
        "model": model_id,
        "use_responses_api": True,
        # Prefer the Responses-shaped AIMessage content format for new work.
        "output_version": "responses/v1",
    }
    if _supports_temperature(model_id):
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)
