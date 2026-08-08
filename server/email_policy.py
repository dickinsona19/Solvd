from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingDecision:
    should_process: bool
    reason: str


_AUTOMATED_SENDERS = re.compile(r"(?:^|[._+-])(no-?reply|do-?not-?reply|mailer-daemon|postmaster)(?:@|[._+-])", re.I)
_AUTOMATED_SUBJECTS = re.compile(
    r"^(?:automatic reply|auto(?:matic)? response|out of office|delivery status notification|undeliverable|failure notice|receipt\b|invoice\b)",
    re.I,
)
_ACTIONABLE = re.compile(
    r"\?|\b(?:can|could|would|please|help|need|want|cancel|freeze|pause|refund|charged|charge|billing|"
    r"book|booking|reserve|reservation|switch|move|change|class|schedule|membership|rate|price|"
    r"trial|pass|join|childcare|parking|hours|injur|hurt|pain|problem|issue|wrong)\b",
    re.I,
)
_ACK_ONLY = re.compile(
    r"^(?:thanks|thank you|got it|okay|ok|sounds good|perfect|great|see you(?: then)?|will do|all set)"
    r"[\s.!,-]*(?:thanks|thank you)?[\s.!]*$",
    re.I,
)


def decide_email(message: dict, support_addresses: set[str] | None = None) -> ProcessingDecision:
    """Use deterministic gates before spending money on an AI call.

    False negatives are more costly than false positives here, so ambiguous
    human-written inbox mail is processed. We skip only strong signals that a
    message is not an inbound request or is an automated/acknowledgement email.
    """

    labels = {str(label).upper() for label in message.get("labels", [])}
    if labels and "INBOX" not in labels:
        return ProcessingDecision(False, "Not an inbox message")
    if labels and "UNREAD" not in labels:
        return ProcessingDecision(False, "Already read before ingestion")
    if {"SPAM", "TRASH", "SENT", "DRAFT"} & labels:
        return ProcessingDecision(False, "Excluded mailbox label")

    sender = str(message.get("from", {}).get("email", "")).strip().lower()
    if not sender:
        return ProcessingDecision(False, "Sender address is missing")
    if support_addresses and sender in {address.lower() for address in support_addresses}:
        return ProcessingDecision(False, "Message was sent by the gym")
    if _AUTOMATED_SENDERS.search(sender):
        return ProcessingDecision(False, "Automated sender")

    headers = {str(key).lower(): str(value).strip() for key, value in message.get("headers", {}).items()}
    auto_submitted = headers.get("auto-submitted", "").lower()
    precedence = headers.get("precedence", "").lower()
    if auto_submitted and auto_submitted != "no":
        return ProcessingDecision(False, "Auto-submitted email")
    if precedence in {"bulk", "junk", "list"} or headers.get("list-id"):
        return ProcessingDecision(False, "Bulk or mailing-list email")

    subject = str(message.get("subject", "")).strip()
    body = re.sub(r"\s+", " ", str(message.get("body_text", ""))).strip()
    if not body:
        return ProcessingDecision(False, "Message body is empty")
    if _AUTOMATED_SUBJECTS.search(subject):
        return ProcessingDecision(False, "Automated notification subject")
    if len(body) <= 120 and _ACK_ONLY.fullmatch(body):
        return ProcessingDecision(False, "Acknowledgement does not need a reply")
    if _ACTIONABLE.search(f"{subject}\n{body}"):
        return ProcessingDecision(True, "Member question or request")

    return ProcessingDecision(True, "Human inbox message; draft for owner review")
