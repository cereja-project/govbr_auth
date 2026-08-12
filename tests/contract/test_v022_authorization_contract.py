"""Preserve the v0.2.2 authorization wire fixture without legacy imports."""

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "govbr_authorization_v022.json"


def test_v022_authorization_fixture_preserves_oauth_and_pkce_wire_fields() -> None:
    authorization = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert authorization == {
        "method": "GET",
        "url": "https://sso.example.test/authorize",
        "query": {
            "client_id": "contract-client",
            "code_challenge": "sanitized-base64url-sha256-challenge",
            "code_challenge_method": "S256",
            "nonce": "sanitized-nonce",
            "redirect_uri": "https://consumer.example.test/oauth/callback",
            "response_type": "code",
            "scope": "openid profile email",
            "state": "sanitized-encrypted-state",
        },
    }
