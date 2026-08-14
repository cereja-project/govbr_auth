"""Installable loopback-only showcase for the complete local Gov.br flow."""

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Protocol

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from pydantic import SecretStr

from govbr_auth.core import (
    ExpiredTransactionError,
    GovBrAuthError,
    GovBrClient,
    GovBrSettings,
    IdTokenValidator,
    InMemoryTransactionStore,
    InvalidIdTokenError,
    InvalidStateError,
    ProviderEnvironment,
)
from govbr_auth.core.errors import ProviderRejectedError, ProviderUnavailableError
from govbr_auth.demo._html import (
    DemoCredential,
    render_error,
    render_home,
    render_success,
)
from govbr_auth.fake import (
    FakeClient,
    FakeCredentialAuthenticator,
    FakeGovBrProvider,
    FakeGovBrSettings,
    FakeSigningKey,
    FakeUser,
    FakeUserStore,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserRepository,
    JsonFakeUserRepository,
    create_fake_govbr_router,
)
from govbr_auth.fastapi import AuthContext, GovBrAuth, utc_now

DEMO_BASE_URL = "http://localhost:8000"
DEMO_PROVIDER_PREFIX = "/fake-govbr"

_DEMO_CLIENT_ID = "govbr-auth-demo"
_DEMO_CLIENT_SECRET = "local-demo-only"
_DEMO_CALLBACK_URL = f"{DEMO_BASE_URL}/auth/govbr/callback"
_DEMO_PROVIDER_URL = f"{DEMO_BASE_URL}{DEMO_PROVIDER_PREFIX}"
_DEMO_USERS = (
    (
        FakeUser(
            sub="12345678901",
            name="Ana Demo",
            email="ana@example.test",
            email_verified=True,
        ),
        SecretStr("ana-demo"),
    ),
    (
        FakeUser(
            sub="98765432100",
            name="Bruno Demo",
            email="bruno@example.test",
            email_verified=True,
        ),
        SecretStr("bruno-demo"),
    ),
)
_DEMO_CREDENTIALS = (
    DemoCredential(cpf="12345678901", password="ana-demo", name="Ana Demo"),
    DemoCredential(cpf="98765432100", password="bruno-demo", name="Bruno Demo"),
)

__all__ = ["DEMO_BASE_URL", "DEMO_PROVIDER_PREFIX", "create_demo_app", "run"]


class FakeUserRepository(FakeUserStore, FakeCredentialAuthenticator, Protocol):
    """Combine fake-user lookup and credential authentication contracts."""


def create_demo_app(
    *,
    clock: Callable[[], datetime] = utc_now,
    user_repository: FakeUserRepository | None = None,
) -> FastAPI:
    """Create the loopback consumer and interactive fake provider showcase."""
    transaction_secret = SecretStr(Fernet.generate_key().decode("ascii"))
    repository, credentials = _resolve_user_repository(user_repository)
    _, fake_router = _create_provider(clock=clock, user_repository=repository)
    provider_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    provider_app.include_router(fake_router)
    provider_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=provider_app))
    settings = _create_consumer_settings(transaction_secret=transaction_secret)
    client = GovBrClient(
        settings,
        InMemoryTransactionStore(transaction_secret),
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

    @application.get("/", include_in_schema=False)
    async def home() -> HTMLResponse:
        return HTMLResponse(
            render_home(credentials=credentials),
            headers={"Cache-Control": "no-store"},
        )

    async def authenticated(context: AuthContext) -> Response:
        return HTMLResponse(
            render_success(context.user),
            headers={"Cache-Control": "no-store"},
        )

    async def authentication_failed(error: GovBrAuthError) -> Response:
        code, status_code = _public_error(error)
        return HTMLResponse(
            render_error(code=code, status_code=status_code),
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    @application.exception_handler(RequestValidationError)
    async def invalid_callback(
        _: Request,
        __: RequestValidationError,
    ) -> HTMLResponse:
        return HTMLResponse(
            render_error(code="invalid_callback", status_code=400),
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )

    @application.exception_handler(Exception)
    async def internal_error(_: Request, __: Exception) -> HTMLResponse:
        return HTMLResponse(
            render_error(code="internal_error", status_code=500),
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    GovBrAuth(
        client=client,
        on_success=authenticated,
        on_error=authentication_failed,
        clock=clock,
    ).install(application)
    application.include_router(fake_router)
    return application


def _create_provider(
    *,
    clock: Callable[[], datetime],
    user_repository: FakeUserRepository,
) -> tuple[FakeGovBrProvider, APIRouter]:
    issuer = f"{_DEMO_PROVIDER_URL}/"
    settings = FakeGovBrSettings(
        base_url=issuer,
        issuer=issuer,
        artifact_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id=_DEMO_CLIENT_ID,
                client_secret=SecretStr(_DEMO_CLIENT_SECRET),
                registered_redirect_uris=(_DEMO_CALLBACK_URL,),
            ),
        ),
    )
    provider = FakeGovBrProvider(
        settings=settings,
        user_store=user_repository,
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=FakeSigningKey.generate(kid="govbr-auth-demo-key"),
    )
    router = create_fake_govbr_router(
        provider,
        prefix=DEMO_PROVIDER_PREFIX,
        credential_authenticator=user_repository,
        clock=clock,
    )
    return provider, router


def _resolve_user_repository(
    explicit: FakeUserRepository | None,
) -> tuple[FakeUserRepository, tuple[DemoCredential, ...]]:
    if explicit is not None:
        return explicit, ()
    json_path = os.environ.get("GOVBR_FAKE_USERS_FILE")
    if json_path:
        return JsonFakeUserRepository.from_file(json_path), ()
    return InMemoryFakeUserRepository(_DEMO_USERS), _DEMO_CREDENTIALS


def _create_consumer_settings(*, transaction_secret: SecretStr) -> GovBrSettings:
    return GovBrSettings(
        environment=ProviderEnvironment.LOCAL,
        authorization_url=f"{_DEMO_PROVIDER_URL}/authorize",
        token_url=f"{_DEMO_PROVIDER_URL}/token",
        userinfo_url=f"{_DEMO_PROVIDER_URL}/userinfo",
        client_id=_DEMO_CLIENT_ID,
        client_secret=SecretStr(_DEMO_CLIENT_SECRET),
        redirect_uri=_DEMO_CALLBACK_URL,
        transaction_secret=transaction_secret,
        issuer=f"{_DEMO_PROVIDER_URL}/",
        jwks_url=f"{_DEMO_PROVIDER_URL}/jwk",
    )


def _public_error(error: GovBrAuthError) -> tuple[str, int]:
    if isinstance(error, InvalidStateError):
        return "invalid_state", 400
    if isinstance(error, ExpiredTransactionError):
        return "expired_transaction", 400
    if isinstance(error, InvalidIdTokenError):
        return "invalid_id_token", 502
    if isinstance(error, ProviderRejectedError):
        return "provider_rejected", 502
    if isinstance(error, ProviderUnavailableError):
        return "provider_unavailable", 503
    return "govbr_auth_error", 502


def run() -> None:
    """Run the showcase only on the fixed IPv4 loopback endpoint."""
    import uvicorn

    uvicorn.run(
        "govbr_auth.demo:create_demo_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )
