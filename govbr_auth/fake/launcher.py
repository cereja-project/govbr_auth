"""Application assembly helpers for the local Fake Gov.br launcher."""

from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse

from govbr_auth.fastapi import AuthContext, GovBrAuth
from govbr_auth.presentation import render_error, render_home, render_success
from govbr_auth.core import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidIdTokenError,
    InvalidStateError,
)
from govbr_auth.core.errors import ProviderRejectedError, ProviderUnavailableError


def create_end_to_end_app(
    runtime,
    *,
    clock: Callable[[], datetime],
    render_success_page: Callable[[object], str] = render_success,
    render_error_page: Callable[..., str] = render_error,
    render_home_page: Callable[..., str] = render_home,
) -> FastAPI:
    """Assemble the consumer facade and its embedded fake provider profile."""

    async def authenticated(context: AuthContext) -> HTMLResponse:
        return HTMLResponse(
            render_success_page(context.user),
            headers={"Cache-Control": "no-store"},
        )

    async def authentication_failed(error: GovBrAuthError) -> HTMLResponse:
        code, status_code = public_error(error)
        return HTMLResponse(
            render_error_page(code=code, status_code=status_code),
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    auth = GovBrAuth(
        runtime=runtime,
        on_success=authenticated,
        on_error=authentication_failed,
        clock=clock,
    )
    fake_runtime = runtime.fake
    if fake_runtime is None:
        raise RuntimeError("end-to-end launcher requires the fake provider runtime")
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @application.get("/", include_in_schema=False)
    async def home() -> HTMLResponse:
        return HTMLResponse(
            render_home_page(credentials=fake_runtime.credentials),
            headers={"Cache-Control": "no-store"},
        )

    @application.exception_handler(RequestValidationError)
    async def invalid_callback(
        _: Request,
        __: RequestValidationError,
    ) -> HTMLResponse:
        return HTMLResponse(
            render_error_page(code="invalid_callback", status_code=400),
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )

    @application.exception_handler(Exception)
    async def internal_error(_: Request, __: Exception) -> HTMLResponse:
        return HTMLResponse(
            render_error_page(code="internal_error", status_code=500),
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    application.include_router(auth.router)
    return application


def public_error(error: GovBrAuthError) -> tuple[str, int]:
    """Map internal authentication failures to stable public error codes."""
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
