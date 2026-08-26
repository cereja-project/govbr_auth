"""Characterize the internal boundaries introduced by the refactoring."""

from datetime import UTC, datetime

import httpx
from cryptography.fernet import Fernet
from fastapi.responses import Response
from pydantic import SecretStr

from govbr_auth.authentication import AuthenticationService
from govbr_auth.core.client import GovBrClient
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import EncryptedTransactionCodec
from govbr_auth.fastapi import create_govbr_router
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings, create_govbr_runtime


def test_official_and_fake_runtime_share_the_same_consumer_stack() -> None:
    """Only provider binding must differ between official and fake consumers."""
    official = create_govbr_runtime(_official_settings())
    fake = create_govbr_runtime(
        GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
            fake_redirect_uri="http://127.0.0.1:8000/auth/govbr/callback",
        ),
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda request: httpx.Response(500, request=request)
        ),
        clock=lambda: datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
    )

    official_service = _route_authentication_services(
        create_govbr_router(client=official.client, on_success=_success_response)
    )
    fake_service = _route_authentication_services(
        create_govbr_router(client=fake.client, on_success=_success_response)
    )

    assert type(official.client) is GovBrClient
    assert type(fake.client) is GovBrClient
    assert type(official.client._transactions) is EncryptedTransactionCodec
    assert type(fake.client._transactions) is EncryptedTransactionCodec
    assert type(official.client._validator) is IdTokenValidator
    assert type(fake.client._validator) is IdTokenValidator
    assert len(official_service) == 1
    assert len(fake_service) == 1
    assert type(official_service[0]) is AuthenticationService
    assert type(fake_service[0]) is AuthenticationService
    assert official_service[0]._client is official.client
    assert fake_service[0]._client is fake.client


async def _success_response(context: object) -> Response:
    del context
    return Response(status_code=204)


def _official_settings() -> GovBrRuntimeSettings:
    return GovBrRuntimeSettings(
        oauth=GovBrSettings(
            authorization_url="https://sso.example.test/authorize",
            token_url="https://sso.example.test/token",
            userinfo_url="https://sso.example.test/userinfo",
            client_id="test-client",
            client_secret=SecretStr("test-client-secret"),
            redirect_uri="https://consumer.example.test/oauth/callback",
            transaction_secret=SecretStr(Fernet.generate_key().decode("ascii")),
            issuer="https://sso.example.test",
            jwks_url="https://sso.example.test/jwks",
        )
    )


def _route_authentication_services(router: object) -> list[AuthenticationService]:
    services: list[AuthenticationService] = []
    seen: set[int] = set()
    for route in getattr(router, "routes", ()):
        closure = getattr(route.endpoint, "__closure__", None) or ()
        for cell in closure:
            value = cell.cell_contents
            if type(value) is AuthenticationService and id(value) not in seen:
                seen.add(id(value))
                services.append(value)
    return services
