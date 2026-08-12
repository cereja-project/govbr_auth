"""Executable FastAPI consumer with an explicit local-provider bootstrap."""

import os
from contextlib import asynccontextmanager
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import SecretStr

from govbr_auth import AuthContext, GovBrAuth
from govbr_auth.core import (
    GovBrClient,
    GovBrSettings,
    IdTokenValidator,
    InMemoryTransactionStore,
    ProviderEnvironment,
)


def utc_now() -> datetime:
    """Return the current UTC time for the example's injectable clock."""
    return datetime.now(UTC)


def settings_from_environment() -> GovBrSettings:
    """Load only provider endpoints, credentials, and transaction configuration."""
    return GovBrSettings(
        environment=ProviderEnvironment(
            os.environ.get("GOVBR_ENVIRONMENT", "production")
        ),
        authorization_url=os.environ["GOVBR_AUTHORIZATION_URL"],
        token_url=os.environ["GOVBR_TOKEN_URL"],
        userinfo_url=os.environ["GOVBR_USERINFO_URL"],
        client_id=os.environ["GOVBR_CLIENT_ID"],
        client_secret=SecretStr(os.environ["GOVBR_CLIENT_SECRET"]),
        redirect_uri=os.environ["GOVBR_REDIRECT_URI"],
        transaction_secret=SecretStr(os.environ["GOVBR_TRANSACTION_SECRET"]),
        issuer=os.environ["GOVBR_ISSUER"],
        jwks_url=os.environ["GOVBR_JWKS_URL"],
    )


def create_app(
    *,
    provider_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Create one consumer whose routes do not depend on the selected provider."""
    settings = settings_from_environment()
    provider_http = httpx.AsyncClient(transport=provider_transport)
    client = GovBrClient(
        settings,
        InMemoryTransactionStore(settings.transaction_secret),
        IdTokenValidator(settings=settings),
        provider_http,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await provider_http.aclose()

    application = FastAPI(lifespan=lifespan)

    async def authenticated(context: AuthContext) -> Response:
        return JSONResponse(
            {
                "authenticated": True,
                "subject": context.user.subject,
            }
        )

    GovBrAuth(client=client, on_success=authenticated, clock=clock).install(application)
    return application


def create_development_app() -> FastAPI:
    """Explicitly mount the optional fake provider for local development."""
    from govbr_auth.fake import (
        FakeClient,
        FakeGovBrProvider,
        FakeGovBrSettings,
        FakeSigningKey,
        FakeUser,
        InMemoryAuthorizationCodeReplayStore,
        InMemoryFakeUserStore,
        create_fake_govbr_router,
    )

    settings = settings_from_environment()
    issuer = str(settings.issuer)
    authorization_path = urlsplit(str(settings.authorization_url)).path
    provider_prefix = authorization_path.removesuffix("/authorize")
    fake_settings = FakeGovBrSettings(
        base_url=issuer,
        issuer=issuer,
        artifact_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id=settings.client_id,
                client_secret=settings.client_secret,
                registered_redirect_uris=(settings.redirect_uri,),
            ),
        ),
    )
    provider = FakeGovBrProvider(
        settings=fake_settings,
        user_store=InMemoryFakeUserStore(
            (
                FakeUser(
                    sub="local-example-subject",
                    name="Local Example User",
                    email="local@example.test",
                    email_verified=True,
                ),
            )
        ),
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=FakeSigningKey.generate(kid="local-example-key"),
    )
    application = create_app()
    application.include_router(
        create_fake_govbr_router(provider, prefix=provider_prefix)
    )
    return application
