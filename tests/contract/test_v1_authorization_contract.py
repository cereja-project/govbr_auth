"""Freeze the Gov.br v1 authorization URL contract."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from govbr_auth.core.models import AuthTransaction
from govbr_auth.core.settings import GovBrSettings

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
AUTHORIZATION_PARAMETERS = {
    "response_type",
    "client_id",
    "scope",
    "redirect_uri",
    "nonce",
    "state",
    "code_challenge",
    "code_challenge_method",
}


@dataclass
class RecordingTransactionCodec:
    """Return a deterministic transaction for contract verification."""

    created: AuthTransaction | None = None

    def issue(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        transaction = AuthTransaction(
            transaction_id="contract-transaction-123",
            code_verifier=SecretStr("pkce-verifier-for-contract-test"),
            nonce=SecretStr("contract-nonce-bound-to-transaction"),
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        self.created = transaction
        return "contract-opaque-sensitive-state", transaction


@pytest.fixture
def settings() -> GovBrSettings:
    """Provide settings configured with the frozen contract values."""
    return GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="contract-client",
        client_secret="contract-client-secret",
        redirect_uri="https://consumer.example.test/oauth/callback",
        transaction_secret="contract-transaction-secret",
        issuer="https://sso.example.test",
        jwks_url="https://sso.example.test/jwk",
    )


def test_build_emits_the_required_authorization_parameters(
    settings: GovBrSettings,
) -> None:
    authorization = import_module("govbr_auth.core.authorization")
    builder = authorization.AuthorizationBuilder(settings, RecordingTransactionCodec())

    request = builder.build(now=FIXED_NOW)

    parsed_url = urlsplit(request.url)
    query = parse_qs(parsed_url.query, strict_parsing=True)

    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "sso.example.test"
    assert parsed_url.path == "/authorize"
    assert set(query) == AUTHORIZATION_PARAMETERS
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["contract-client"]
    assert query["scope"] == ["openid profile email"]
    assert query["redirect_uri"] == ["https://consumer.example.test/oauth/callback"]
    assert query["state"] == [request.state]
    assert query["code_challenge_method"] == ["S256"]
