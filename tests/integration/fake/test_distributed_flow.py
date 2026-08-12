"""Distributed HTTP flow tests for explicit Fake Gov.br provider instances."""

import json
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from govbr_auth.core import (
    GovBrClient,
    GovBrSettings,
    IdTokenValidator,
    InMemoryTransactionStore,
    ProviderEnvironment,
)
from govbr_auth.fake import (
    FakeClient,
    FakeGovBrProvider,
    FakeGovBrSettings,
    FakeSigningKey,
    FakeUser,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
    create_fake_govbr_app,
)

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class OpaqueRequestParser(HTMLParser):
    """Extract the opaque authorization request from fake login HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.request_artifact: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name") == "request":
            self.request_artifact = attributes.get("value")


def build_provider(
    *,
    settings: FakeGovBrSettings,
    signing_key: FakeSigningKey,
    user: FakeUser,
) -> FakeGovBrProvider:
    """Build one provider with stores independent from every other instance."""
    return FakeGovBrProvider(
        settings=settings,
        user_store=InMemoryFakeUserStore((user,)),
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=signing_key,
    )


def parse_request_artifact(document: str) -> str | None:
    """Return the opaque browser request carried by the login form."""
    parser = OpaqueRequestParser()
    parser.feed(document)
    return parser.request_artifact


def oauth_values(location: str) -> dict[str, list[str]]:
    """Return decoded OAuth query values from a redirect location."""
    return parse_qs(urlsplit(location).query)


@pytest.mark.asyncio
async def test_distributed_flow_accepts_consumed_code_on_fresh_provider_due_to_documented_fake_only_replay_limitation() -> (
    None
):
    """Document that fake cross-instance replay is not shared without a replay store."""
    artifact_secret = SecretStr(Fernet.generate_key().decode("ascii"))
    signing_key = FakeSigningKey.generate(kid="shared-fake-provider-key")
    user = FakeUser(
        sub="12345678900",
        name="Maria da Silva",
        email="maria@example.test",
        email_verified=True,
    )
    provider_settings = FakeGovBrSettings(
        base_url="http://localhost/",
        issuer="http://localhost/",
        artifact_secret=artifact_secret,
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id="distributed-client",
                client_secret=SecretStr("distributed-client-secret"),
                registered_redirect_uris=("http://localhost/callback",),
            ),
        ),
    )
    provider_a = build_provider(
        settings=provider_settings,
        signing_key=signing_key,
        user=user,
    )
    provider_b = build_provider(
        settings=provider_settings,
        signing_key=signing_key,
        user=user,
    )
    provider_c = build_provider(
        settings=provider_settings,
        signing_key=signing_key,
        user=user,
    )
    transaction_secret = SecretStr(Fernet.generate_key().decode("ascii"))
    consumer_settings = GovBrSettings(
        environment=ProviderEnvironment.LOCAL,
        authorization_url="http://localhost/authorize",
        token_url="http://localhost/token",
        userinfo_url="http://localhost/userinfo",
        client_id="distributed-client",
        client_secret=SecretStr("distributed-client-secret"),
        redirect_uri="http://localhost/callback",
        transaction_secret=transaction_secret,
        issuer="http://localhost/",
        jwks_url="http://localhost/jwk",
        clock_skew_seconds=0,
    )
    transactions = InMemoryTransactionStore(transaction_secret)
    application_a = create_fake_govbr_app(provider_a, clock=lambda: FIXED_NOW)
    application_b = create_fake_govbr_app(provider_b, clock=lambda: FIXED_NOW)
    application_c = create_fake_govbr_app(provider_c, clock=lambda: FIXED_NOW)

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application_a),
            base_url="http://localhost",
        ) as http_a,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application_b),
            base_url="http://localhost",
        ) as http_b,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application_c),
            base_url="http://localhost",
        ) as http_c,
    ):
        client = GovBrClient(
            consumer_settings,
            transactions,
            IdTokenValidator(settings=consumer_settings),
            http_b,
        )
        authorization = client.authorization_url(now=FIXED_NOW)
        transaction_payload = json.loads(
            Fernet(transaction_secret.get_secret_value().encode("ascii"))
            .decrypt(authorization.state.encode("ascii"))
            .decode("utf-8")
        )
        authorize_response = await http_a.get(authorization.url)
        request_artifact = parse_request_artifact(authorize_response.text)
        login_response = await http_b.post(
            "/login",
            data={"request": request_artifact, "subject": user.sub},
        )
        redirect_values = oauth_values(login_response.headers["location"])
        code = redirect_values["code"][0]
        result = await client.exchange_code(
            code=code,
            state=redirect_values["state"][0],
            now=FIXED_NOW,
        )
        resolved_user = await client.userinfo(
            result.tokens.access_token,
            expected_subject=result.id_token_claims["sub"],
        )
        token_form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost/callback",
            "code_verifier": transaction_payload["code_verifier"],
        }
        replay_on_b = await http_b.post(
            "/token",
            auth=("distributed-client", "distributed-client-secret"),
            data=token_form,
        )
        replay_on_fresh_c = await http_c.post(
            "/token",
            auth=("distributed-client", "distributed-client-secret"),
            data=token_form,
        )

    assert authorize_response.status_code == 200
    assert login_response.status_code == 302
    assert result.id_token_claims["sub"] == user.sub
    assert result.id_token_claims["nonce"] == transaction_payload["nonce"]
    assert resolved_user.model_dump() == user.model_dump()
    assert replay_on_b.status_code == 400
    assert replay_on_b.json() == {
        "error": "invalid_grant",
        "error_description": "The authorization code is invalid or expired.",
    }
    assert replay_on_fresh_c.status_code == 200
    assert replay_on_fresh_c.json()["token_type"] == "Bearer"
