"""Focused tests for the extracted OAuth HTTP transport."""

import base64

import httpx
import pytest
from pydantic import SecretStr

from govbr_auth.core.errors import ProviderUnavailableError
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.transport import GovBrHttpTransport


@pytest.fixture
def settings() -> GovBrSettings:
    return GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="test-client",
        client_secret=SecretStr("sensitive-client-secret"),
        redirect_uri="https://consumer.example.test/callback",
        transaction_secret=SecretStr("sensitive-transaction-secret"),
        issuer="https://sso.example.test",
        jwks_url="https://sso.example.test/jwk",
        connect_timeout_seconds=2,
        read_timeout_seconds=3,
    )


@pytest.mark.asyncio
async def test_post_token_applies_provider_auth_and_configured_timeout(
    settings: GovBrSettings,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        transport = GovBrHttpTransport(settings, http)
        response = await transport.post_token({"code": "authorization-code"})

    assert response.status_code == 200
    assert requests[0].method == "POST"
    assert str(requests[0].url) == str(settings.token_url)
    assert requests[0].headers["authorization"] == (
        "Basic "
        + base64.b64encode(b"test-client:sensitive-client-secret").decode("ascii")
    )


@pytest.mark.asyncio
async def test_get_userinfo_applies_bearer_authorization(
    settings: GovBrSettings,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        return httpx.Response(200, json={"sub": "subject"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        transport = GovBrHttpTransport(settings, http)

        await transport.get_userinfo(SecretStr("sensitive-access-token"))

    assert requests[0].method == "GET"
    assert str(requests[0].url) == str(settings.userinfo_url)

    assert requests[0].headers["authorization"] == "Bearer sensitive-access-token"


@pytest.mark.asyncio
async def test_transport_sanitizes_timeout_failures(settings: GovBrSettings) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive provider detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        transport = GovBrHttpTransport(settings, http)

        with pytest.raises(
            ProviderUnavailableError,
            match="Gov.br provider request timed out",
        ) as error:
            await transport.get_jwks()

    assert isinstance(error.value.__cause__, RuntimeError)
    assert str(error.value.__cause__) == ("Gov.br HTTP transport failed (ReadTimeout)")
    assert "sensitive provider detail" not in str(error.value.__cause__)
