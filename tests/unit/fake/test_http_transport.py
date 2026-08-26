"""Tests for the framework-neutral in-process FakeGov transport."""

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from govbr_auth.fake.models import FakeUser
from govbr_auth.fake.provider import (
    FakeTokenResponse,
)

FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class ProviderStub:
    credential_authenticator = None
    prefix = "/fake-govbr"

    def __init__(self) -> None:
        self.provider = self
        self.user = FakeUser(sub="12345678900", name="Fake user", email="fake@test")

    def exchange_code(self, **_: object) -> FakeTokenResponse:
        return FakeTokenResponse(
            access_token=SecretStr("access-token"),
            expires_in=300,
            id_token=SecretStr("id-token"),
            scope="openid profile email",
        )

    def jwks(self) -> dict[str, object]:
        return {"keys": []}

    def userinfo(self, access_token: SecretStr, *, now: datetime) -> FakeUser:
        return self.user


def test_transport_reuses_runtime_http_application() -> None:
    """Transport calls must share the simulator-owned neutral HTTP application."""
    from govbr_auth.fake.http.application import FakeGovHttpApplication
    from govbr_auth.fake.http.transport import FakeGovHttpTransport

    runtime = ProviderStub()
    runtime.http_application = FakeGovHttpApplication(runtime, clock=lambda: FIXED_NOW)

    transport = FakeGovHttpTransport(runtime, clock=lambda: FIXED_NOW)

    assert transport._application is runtime.http_application


@pytest.mark.asyncio
async def test_transport_serves_token_jwks_and_userinfo_without_fastapi() -> None:
    from govbr_auth.fake.http.transport import FakeGovHttpTransport

    async with httpx.AsyncClient(
        transport=FakeGovHttpTransport(ProviderStub(), clock=lambda: FIXED_NOW),
        base_url="http://fake.test",
    ) as client:
        token = await client.post(
            "/fake-govbr/token",
            auth=("client", "secret"),
            data={
                "grant_type": "authorization_code",
                "code": "code",
                "redirect_uri": "http://consumer.test/callback",
                "code_verifier": "verifier",
            },
        )
        jwks = await client.get("/fake-govbr/jwk")
        userinfo = await client.get(
            "/fake-govbr/userinfo",
            headers={"Authorization": "Bearer access-token"},
        )

    assert token.status_code == 200
    assert token.json()["access_token"] == "access-token"
    assert jwks.json() == {"keys": []}
    assert userinfo.json()["sub"] == "12345678900"
