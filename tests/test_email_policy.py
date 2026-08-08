from server.email_policy import decide_email


def message(body: str, **overrides) -> dict:
    value = {
        "from": {"name": "Member", "email": "member@example.com"},
        "subject": "Question",
        "body_text": body,
        "labels": ["INBOX", "UNREAD"],
        "headers": {},
    }
    value.update(overrides)
    return value


def test_processes_member_questions_and_requests():
    assert decide_email(message("Can I freeze my membership next month?")).should_process
    assert decide_email(message("I was charged twice and need a refund.")).should_process


def test_skips_acknowledgements_without_calling_ai():
    decision = decide_email(message("Sounds good, thank you"))
    assert not decision.should_process
    assert "Acknowledgement" in decision.reason


def test_skips_automated_and_bulk_mail():
    assert not decide_email(
        message("Your report is ready", **{"from": {"name": "Bot", "email": "no-reply@example.com"}})
    ).should_process
    assert not decide_email(
        message("Newsletter", headers={"Precedence": "bulk"})
    ).should_process


def test_skips_messages_sent_by_the_gym():
    decision = decide_email(
        message("Internal note", **{"from": {"name": "Gym", "email": "front@gym.test"}}),
        {"front@gym.test"},
    )
    assert not decision.should_process
