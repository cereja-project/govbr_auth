"""Preserve the v0.2.2 token wire fixture without legacy imports."""

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "govbr_token_success.json"


def test_v022_token_fixture_preserves_success_response_wire_fields() -> None:
    token_response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert token_response == {
        "access_token": "sanitized-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid profile email",
        "id_token": (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJzYW5pdGl6ZWQtc3ViamVjdCIsImlzcyI6Imh0dHBzOi8v"
            "c3NvLmV4YW1wbGUudGVzdCIsImV4cCI6NDEwMjQ0NDgwMCwiaWF0IjoxNzA0"
            "MDY3MjAwLCJub25jZSI6InNhbml0aXplZC1ub25jZSJ9."
            "gCscxICo4Yr9Xj7aE7nBH5gu3-DLx3KSABadSM3UwqU"
        ),
    }
