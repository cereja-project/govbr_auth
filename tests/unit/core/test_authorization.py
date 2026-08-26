"""Tests for OAuth authorization request construction."""

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from govbr_auth.core.models import AuthTransaction
from govbr_auth.core.settings import GovBrSettings

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@dataclass
class RecordingTransactionCodec:
    """Return a deterministic transaction and retain the issue call result."""

    created: AuthTransaction | None = None

    def issue(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        transaction = AuthTransaction(
            transaction_id="transaction-123",
            code_verifier=SecretStr("pkce-verifier-for-authorization-test"),
            nonce=SecretStr("nonce-bound-to-transaction"),
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        self.created = transaction
        return "opaque-sensitive-state", transaction


@pytest.fixture
def settings() -> GovBrSettings:
    """Provide valid provider settings for a deterministic authorization URL."""
    return GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="authorization-client",
        client_secret="authorization-client-secret",
        redirect_uri="https://consumer.example.test/oauth/callback",
        transaction_secret="transaction-secret",
        issuer="https://sso.example.test",
        jwks_url="https://sso.example.test/jwk",
    )


@pytest.fixture
def recording_transaction_codec() -> RecordingTransactionCodec:
    """Provide an isolated transaction-codec test double."""
    return RecordingTransactionCodec()


def test_build_binds_state_nonce_and_pkce_to_created_transaction(
    settings: GovBrSettings,
    recording_transaction_codec: RecordingTransactionCodec,
) -> None:
    authorization = import_module("govbr_auth.core.authorization")
    builder = authorization.AuthorizationBuilder(settings, recording_transaction_codec)

    request = builder.build(now=FIXED_NOW)

    query = parse_qs(urlsplit(request.url).query, strict_parsing=True)

    assert recording_transaction_codec.created is not None
    assert request.state == "opaque-sensitive-state"
    assert query["state"] == [request.state]
    assert query["nonce"] == [
        recording_transaction_codec.created.nonce.get_secret_value()
    ]
    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                recording_transaction_codec.created.code_verifier.get_secret_value().encode(
                    "ascii"
                )
            ).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    assert query["code_challenge"] == [expected_challenge]
    assert query["code_challenge_method"] == ["S256"]
