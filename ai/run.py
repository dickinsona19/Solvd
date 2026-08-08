"""Run the Smart Inbox agent over demo/data/inbox.json and cache the results.

The demo is a static site: there is no server, and the API key never leaves
this machine. So the agent runs here, offline, and writes what it produced to
demo/data/inbox-ai.json. The browser reads that file and never calls OpenAI,
which is why refreshing the demo is free.

Each email is fingerprinted from its own content plus the models and prompts
that produced the result. Matching fingerprint means the answer is already in
the cache and the email is skipped, so a given message costs exactly one pass.
Editing the message or the prompts changes the fingerprint and re-runs it.

    python ai/run.py                 # only emails with no cached result
    python ai/run.py --force         # re-run everything
    python ai/run.py --only kayla-freeze
    python ai/run.py --list          # report cache state, call nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import dotenv

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "demo" / "data" / "inbox.json"
CACHE = ROOT / "demo" / "data" / "inbox-ai.json"
PROMPTS = Path(__file__).resolve().parent / "prompts.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def recipe_hash() -> str:
    """Identifies the prompt set. Editing prompts.py invalidates the cache."""
    return hashlib.sha256(PROMPTS.read_bytes()).hexdigest()[:12]


def explain(error: Exception) -> str:
    """Turn the usual OpenAI failures into something actionable."""
    text = str(error)
    if "insufficient_quota" in text or "credit_balance_exhausted" in text:
        return (
            "the OpenAI account behind this key has no credits. Add credits and "
            "run this again. Results already cached are kept, so nothing gets "
            "paid for twice."
        )
    if "invalid_api_key" in text or "Incorrect API key" in text:
        return f"OPENAI_API_KEY was rejected. Check the value in {ROOT / '.env'}."
    if "model_not_found" in text or "does not exist" in text:
        return (
            "that model is not available on this account. Override it by setting "
            "SOLVD_SORT_MODEL or SOLVD_DRAFT_MODEL in .env."
        )
    return text.strip().splitlines()[0]


def fingerprint(email: dict, models: dict, recipe: str) -> str:
    """A stable id for "this email, run this way".

    Only the fields the model actually sees are included, so cosmetic edits
    elsewhere in inbox.json do not trigger a re-run.
    """
    payload = json.dumps(
        {
            "name": email.get("name"),
            "meta": email.get("meta"),
            "risk": email.get("risk"),
            "subject": email.get("subject"),
            "message": email.get("message"),
            "models": models,
            "recipe": recipe,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the cache")
    parser.add_argument("--only", metavar="ID", help="process a single email id")
    parser.add_argument(
        "--list", action="store_true", help="show cache state without calling the API"
    )
    args = parser.parse_args()

    dotenv.load_dotenv(ROOT / ".env")

    threads = read_json(INBOX).get("threads", [])
    if missing := [t.get("subject") for t in threads if not t.get("id")]:
        print(f"Every thread needs an id. Missing on: {missing}", file=sys.stderr)
        return 1

    cache = read_json(CACHE) if CACHE.exists() else {}
    results = cache.get("results", {})

    # Imported lazily so --list and the id check work without the AI deps.
    if not args.list:
        if not os.getenv("OPENAI_API_KEY"):
            print(f"OPENAI_API_KEY is not set. Add it to {ROOT / '.env'}.", file=sys.stderr)
            return 1
        try:
            from .graph import build_graph
            from .model import DRAFT_MODEL, SORT_MODEL
        except ImportError:  # Direct `python ai/run.py` compatibility.
            from graph import build_graph
            from model import DRAFT_MODEL, SORT_MODEL

        models = {"sort": SORT_MODEL, "draft": DRAFT_MODEL}
    else:
        models = cache.get("models", {"sort": "", "draft": ""})

    recipe = recipe_hash()
    todo = []
    for email in threads:
        if args.only and email["id"] != args.only:
            continue
        cached = results.get(email["id"])
        fresh = cached and cached.get("fingerprint") == fingerprint(email, models, recipe)
        if args.list:
            print(f"  {'cached ' if fresh else 'stale  '} {email['id']}")
        elif fresh and not args.force:
            print(f"  cached  {email['id']}")
        else:
            todo.append(email)

    if args.list:
        return 0

    if args.only and not todo and not any(t["id"] == args.only for t in threads):
        print(f"No email with id {args.only!r}.", file=sys.stderr)
        return 1

    failed = False
    if todo:
        print(f"Running {len(todo)} email(s) through {models['sort']} + {models['draft']}")
        graph = build_graph()

        for email in todo:
            try:
                state = graph.invoke({"email": email})
            except Exception as error:  # noqa: BLE001 - the message is the point
                # Stop on the first failure rather than burning the rest of the
                # inbox against the same broken key or quota.
                print(f"  failed  {email['id']}: {explain(error)}", file=sys.stderr)
                failed = True
                break

            sort, draft = state["sort"], state["draft"]
            results[email["id"]] = {
                "fingerprint": fingerprint(email, models, recipe),
                "processedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sort": sort,
                "draft": draft,
            }
            flag = ", needs a human" if sort["needs_human"] else ""
            print(
                f"  done    {email['id']}: {sort['category']}/{sort['priority']}"
                f", draft confidence {draft['confidence']}{flag}"
            )

    # Drop results for emails that no longer exist.
    live = {email["id"] for email in threads}
    for stale in set(results) - live:
        del results[stale]
        print(f"  pruned  {stale}")

    write_json(
        CACHE,
        {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "models": models,
            "recipe": recipe,
            "results": dict(sorted(results.items())),
        },
    )
    print(f"Wrote {CACHE.relative_to(ROOT)} ({len(results)} cached)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
