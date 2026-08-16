"""Installable loopback-only showcase for the complete local Gov.br flow."""

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from pydantic import SecretStr

from govbr_auth.core import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidIdTokenError,
    InvalidStateError,
)
from govbr_auth.core.errors import ProviderRejectedError, ProviderUnavailableError
from govbr_auth.demo._html import (
    DemoCredential,
    render_error,
    render_home,
    render_success,
)
from govbr_auth.fake import (
    FakeCredentialAuthenticator,
    FakeUserStore,
)
from govbr_auth.fastapi import AuthContext, GovBrAuth, utc_now
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

DEMO_BASE_URL = "http://localhost:8000"
DEMO_PROVIDER_PREFIX = "/fake-govbr"

_DEMO_CLIENT_ID = "govbr-auth-demo"
_DEMO_CLIENT_SECRET = "local-demo-only"
_DEMO_CALLBACK_URL = f"{DEMO_BASE_URL}/auth/govbr/callback"

__all__ = ["DEMO_BASE_URL", "DEMO_PROVIDER_PREFIX", "create_demo_app", "run"]


class FakeUserRepository(FakeUserStore, FakeCredentialAuthenticator, Protocol):
    """Combine fake-user lookup and credential authentication contracts."""


def create_demo_app(
    *,
    clock: Callable[[], datetime] = utc_now,
    user_repository: FakeUserRepository | None = None,
) -> FastAPI:
    """Create the loopback consumer and interactive fake provider showcase."""

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

    settings = GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_end_to_end=True,
        fake_host="localhost",
        fake_port=8000,
        fake_provider_prefix=DEMO_PROVIDER_PREFIX,
        fake_client_id=_DEMO_CLIENT_ID,
        fake_client_secret=SecretStr(_DEMO_CLIENT_SECRET),
        fake_redirect_uri=_DEMO_CALLBACK_URL,
        fake_users_file=(
            Path(users_file)
            if (users_file := os.environ.get("GOVBR_FAKE_USERS_FILE"))
            else None
        ),
    )
    auth = GovBrAuth(
        settings=settings,
        on_success=authenticated,
        on_error=authentication_failed,
        clock=clock,
        user_repository=user_repository,
    )
    fake_runtime = auth.runtime.fake
    if fake_runtime is None:
        raise RuntimeError("demo requires the fake provider runtime")
    credentials = tuple(
        DemoCredential(
            cpf=credential.cpf,
            password=credential.password,
            name=credential.name,
        )
        for credential in fake_runtime.credentials
    )
    application = FastAPI()

    @application.get("/", include_in_schema=False)
    async def home() -> HTMLResponse:
        return HTMLResponse(
            render_home(credentials=credentials),
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

    application.include_router(auth.router)
    return application


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
