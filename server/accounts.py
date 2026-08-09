from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import ROOT

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
_RAW_FILES = ("account", "members", "visits", "charges", "posts", "pass_claims")


def _account_dir(account_id: str) -> Path:
    if not _SAFE_ID.fullmatch(account_id):
        raise ValueError("Invalid account id")
    return ROOT / "accounts" / account_id


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_account_ids() -> tuple[str, ...]:
    """Discover deploy-time account fixtures without trusting path input."""
    accounts_root = ROOT / "accounts"
    return tuple(
        sorted(
            folder.name
            for folder in accounts_root.iterdir()
            if folder.is_dir()
            and _SAFE_ID.fullmatch(folder.name)
            and (folder / "account.json").is_file()
        )
    )


@lru_cache(maxsize=16)
def static_account_data(account_id: str) -> dict:
    folder = _account_dir(account_id)
    return {name: _read(folder / f"{name}.json") for name in _RAW_FILES}


def fixture_messages(account_id: str) -> list[dict]:
    """Return the temporary raw-email feed for an account."""
    return _read(_account_dir(account_id) / "messages.json")


def fixture_results(account_id: str) -> dict[str, dict]:
    """Return optional precomputed drafts used only by local development."""
    path = _account_dir(account_id) / "inbox-ai.json"
    return _read(path).get("results", {}) if path.is_file() else {}


def member_id_for_email(account_id: str, email: str) -> str | None:
    needle = email.strip().lower()
    for member in static_account_data(account_id)["members"]:
        if str(member.get("email", "")).lower() == needle:
            return member["id"]
    return None


def message_context(account_id: str, message: dict) -> dict:
    data = static_account_data(account_id)
    account = data["account"]
    member = next(
        (item for item in data["members"] if item["id"] == message.get("member_id")),
        None,
    )
    plans = {plan["id"]: plan for plan in account.get("plans", [])}
    context = {
        "name": message["from"]["name"],
        "subject": message["subject"],
        "message": message["body_text"],
        "receivedAt": message["received_at"],
    }
    if member:
        plan = plans.get(member.get("plan_id"), {})
        price = int(plan.get("price_cents", 0)) / 100
        context["meta"] = (
            f"Member since {member.get('joined_at', 'unknown')} · "
            f"{plan.get('name', 'Membership')} · ${price:,.0f}/mo"
        )
    else:
        context["meta"] = f"New lead · {message['from']['email']}"
    return context


def prompt_context(account_id: str) -> tuple[str, str, str]:
    account = static_account_data(account_id)["account"]
    gym = account["gym"]
    plans = account.get("plans", [])
    slots = account.get("class_slots", [])
    plan_lines = ", ".join(
        f"{plan['name']} at ${int(plan['price_cents']) / 100:,.0f}/mo" for plan in plans
    )
    slot_lines = ", ".join(slot["label"] for slot in slots)
    integrations = {item["id"]: item["name"] for item in account.get("integrations", [])}
    booking_tool = integrations.get("mindbody", "the booking system")
    billing_tool = integrations.get("stripe", "the billing system")
    company_name = gym["name"]
    info = (
        f"{company_name} is a strength gym in {gym.get('city', 'its local area')}. "
        f"Plans: {plan_lines}. Class schedule: {slot_lines}. "
        f"Bookings and memberships run through {booking_tool}. "
        f"Billing runs through {billing_tool}. Do not claim the gym has an amenity "
        "or policy that is not explicitly listed here."
    )

    reduced_plan = next((plan for plan in plans if "3x" in plan["name"].lower()), None)
    reduced_offer = (
        f"a move to the {reduced_plan['name']} plan at "
        f"${int(reduced_plan['price_cents']) / 100:,.0f}/mo"
        if reduced_plan
        else "a lower-frequency plan, after the owner confirms its price"
    )
    policy = f"""
You may commit to the following without asking anyone:
- Freezes of up to 60 days. A freeze pauses billing and keeps the current rate locked.
- One plan change per billing cycle, effective the following Monday.
- Refunding a clearly duplicate charge. Refunds land in three to five business days.
- Booking, moving or cancelling a class reservation.
- Honouring a free pass for any class in the week it was claimed.

For a member who wants to cancel, offer a pause of up to 60 days at no cost first.
If that does not fit, the next allowed offer is {reduced_offer}. Offer only one option
at a time. Do not say a system action has already happened unless the action field
names that exact pending action for the owner to approve.

Do not invent policies, discounts, prices, classes, medical advice or amenities.
When the request is outside this list, say that you are checking with the owner and
set needs_human to true.
""".strip()
    return company_name, info, policy
