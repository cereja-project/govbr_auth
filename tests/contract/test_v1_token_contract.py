"""Freeze the Gov.br 1.0 token request wire contract."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from govbr_auth.core.client import GovBrClient
from govbr_auth.core.models import AuthTransaction
from govbr_auth.core.settings import GovBrSettings

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class ContractTransactionCodec:
    """Expose fixed PKCE and nonce inputs for the token request contract."""

    def issue(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        return "contract-state", self._transaction(now)

    def decode(self, state: str, *, now: datetime) -> AuthTransaction:
        return self._transaction(now)

    @staticmethod
    def _transaction(now: datetime) -> AuthTransaction:
        return AuthTransaction(
            transaction_id="contract-transaction",
            code_verifier=SecretStr("v" * 43),
            nonce=SecretStr("contract-nonce"),
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
        )


class ContractIdTokenValidator:
    """Return fixed verified claims for the HTTP wire contract test."""

    def validate(
        self,
        id_token: SecretStr,
        expected_nonce: SecretStr,
        *,
        jwks: Mapping[str, object],
        now: datetime,
    ) -> Mapping[str, object]:
        return {"sub": "12345678900", "nonce": expected_nonce.get_secret_value()}


@pytest.mark.asyncio
async def test_exchange_code_preserves_token_wire_contract() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"keys": [{"kid": "contract-key"}]})
        return httpx.Response(
            200,
            json={
                "access_token": "contract-access-token",
                "id_token": "contract-id-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid profile email",
            },
        )

    settings = GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="contract-client",
        client_secret=SecretStr("contract-client-secret"),
        redirect_uri="https://consumer.example.test/oauth/callback",
        transaction_secret=SecretStr("contract-transaction-secret"),
        issuer="https://sso.example.test",
        jwks_url="https://sso.example.test/jwk",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(
            settings,
            ContractTransactionCodec(),
            ContractIdTokenValidator(),
            http,
        )

        result = await client.exchange_code(
            code="contract-authorization-code",
            state="contract-state",
            now=FIXED_NOW,
        )

    request = requests[0]
    assert request.method == "POST"
    assert request.url == httpx.URL("https://sso.example.test/token")
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert (
        request.headers["authorization"]
        == "Basic Y29udHJhY3QtY2xpZW50OmNvbnRyYWN0LWNsaWVudC1zZWNyZXQ="
    )
    assert parse_qs(
        request.content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
    ) == {
        "grant_type": ["authorization_code"],
        "code": ["contract-authorization-code"],
        "redirect_uri": ["https://consumer.example.test/oauth/callback"],
        "code_verifier": ["v" * 43],
    }
    assert result.tokens.access_token.get_secret_value() == "contract-access-token"
    assert result.id_token_claims["sub"] == "12345678900"
