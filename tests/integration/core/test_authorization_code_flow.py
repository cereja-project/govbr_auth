"""Integration tests for the framework-independent OAuth core."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from govbr_auth import core
from govbr_auth.core import (
    AuthenticationResult,
    GovBrAuthError,
    GovBrClient,
    GovBrSettings,
    IdTokenValidator,
    InMemoryTransactionStore,
    InvalidIdTokenError,
    ProviderEnvironment,
)
from tests.integration.core.provider import GovBrAsgiProvider

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def rsa_signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def provider(rsa_signing_key: rsa.RSAPrivateKey) -> GovBrAsgiProvider:
    return GovBrAsgiProvider(signing_key=rsa_signing_key, now=FIXED_NOW)


@pytest.fixture
def settings(provider: GovBrAsgiProvider) -> GovBrSettings:
    return GovBrSettings(
        environment=ProviderEnvironment.LOCAL,
        authorization_url=provider.authorization_url,
        token_url=f"{provider.base_url}/token",
        userinfo_url=f"{provider.base_url}/userinfo",
        client_id=provider.client_id,
        client_secret=SecretStr(provider.client_secret),
        redirect_uri=provider.redirect_uri,
        transaction_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        issuer=provider.issuer,
        jwks_url=f"{provider.base_url}/jwk",
        clock_skew_seconds=0,
    )


@pytest_asyncio.fixture
async def core_client(
    provider: GovBrAsgiProvider,
    settings: GovBrSettings,
) -> AsyncIterator[GovBrClient]:
    transport = httpx.ASGITransport(app=provider)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=provider.base_url,
    ) as http:
        jwks_response = await http.get(str(settings.jwks_url))
        jwks_response.raise_for_status()
        validator = IdTokenValidator(settings=settings, jwks=jwks_response.json())
        transactions = InMemoryTransactionStore(settings.transaction_secret)
        yield GovBrClient(settings, transactions, validator, http)


@pytest.mark.asyncio
async def test_core_completes_authorization_code_flow_with_rs256_provider(
    core_client: GovBrClient,
    provider: GovBrAsgiProvider,
) -> None:
    authorization = core_client.authorization_url(now=FIXED_NOW)
    code = provider.authorize(authorization.url)

    result = await core_client.exchange_code(
        code=code,
        state=authorization.state,
        now=FIXED_NOW,
    )
    user = await core_client.userinfo(result.tokens.access_token)

    assert isinstance(result, AuthenticationResult)
    assert result.id_token_claims["nonce"] == provider.last_nonce
    assert user.sub == "12345678900"


@pytest.mark.asyncio
async def test_core_rejects_provider_id_token_with_different_nonce(
    core_client: GovBrClient,
    provider: GovBrAsgiProvider,
) -> None:
    provider.override_nonce("attacker-nonce")
    authorization = core_client.authorization_url(now=FIXED_NOW)
    code = provider.authorize(authorization.url)

    with pytest.raises(
        InvalidIdTokenError,
        match="ID token nonce does not match the authorization transaction",
    ):
        await core_client.exchange_code(
            code=code,
            state=authorization.state,
            now=FIXED_NOW,
        )


@pytest.mark.asyncio
async def test_core_rejects_userinfo_request_with_invalid_bearer_token(
    core_client: GovBrClient,
) -> None:
    invalid_access_token = SecretStr("invalid-access-token")

    with pytest.raises(GovBrAuthError, match="Gov.br rejected the access token"):
        await core_client.userinfo(invalid_access_token)


def test_core_exports_experimental_and_legacy_public_api() -> None:
    assert set(core.__all__) == {
        "AuthenticationResult",
        "AuthTransaction",
        "AuthorizationBuilder",
        "AuthorizationRequest",
        "ExpiredTransactionError",
        "GovBrAddress",
        "GovBrAuthError",
        "GovBrAuthorize",
        "GovBrClient",
        "GovBrConfig",
        "GovBrIntegration",
        "GovBrSettings",
        "GovBrUser",
        "IdTokenValidator",
        "InMemoryTransactionStore",
        "InvalidIdTokenError",
        "InvalidStateError",
        "ProviderEnvironment",
        "TokenSet",
        "TransactionStore",
    }
