from email.message import EmailMessage

from server.ingest import parse_email


def test_parses_plain_text_email_for_ingestion():
    source = EmailMessage()
    source["From"] = "Jordan Member <jordan@example.com>"
    source["To"] = "front@northsidebarbell.com"
    source["Subject"] = "Freeze request"
    source["Message-ID"] = "<message-123@example.com>"
    source["Date"] = "Fri, 07 Aug 2026 20:40:00 -0400"
    source.set_content("Can I freeze my membership for September?")

    parsed = parse_email(source.as_bytes(), "42")

    assert parsed["id"] == "message-123@example.com"
    assert parsed["from"]["email"] == "jordan@example.com"
    assert parsed["subject"] == "Freeze request"
    assert "freeze my membership" in parsed["body_text"]
