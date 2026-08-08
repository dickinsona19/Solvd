import time

import pytest

from server.auth import create_session, verify_token


def test_session_round_trip():
    session = create_session("test", "1234")
    assert session is not None
    payload = verify_token(session["token"])
    assert payload["account"] == "test"
    assert payload["exp"] > time.time()


def test_wrong_password_is_rejected():
    assert create_session("test", "wrong") is None


def test_tampered_token_is_rejected():
    session = create_session("test", "1234")
    with pytest.raises(Exception):
        verify_token(session["token"] + "x")
