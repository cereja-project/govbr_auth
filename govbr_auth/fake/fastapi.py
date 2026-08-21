"""Explicit FastAPI and ASGI factories for the local Fake Gov.br provider."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import SecretStr
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException

from govbr_auth.fake._html import render_fake_login, render_fake_user_selection
from govbr_auth.fake.http.parsing import (
    parse_basic_authorization,
    parse_bearer_authorization,
    required_text_values,
)
from govbr_auth.fake.http.responses import (
    boundary_error_response,
    oauth_error_response,
)
from govbr_auth.fake.credentials import FakeCredentialAuthenticator
from govbr_auth.fake.provider import (
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeGovBrProvider,
    FakeOAuthError,
    FakeTokenRequest,
)
from govbr_auth.fake.runtime import (
    FakeGovBrRuntime,
    FakeUserRepository,
    create_fake_govbr_runtime,
)
from govbr_auth.fastapi import AuthContext, GovBrAuth, utc_now
from govbr_auth.presentation import render_error, render_home, render_success
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntimeSettings,
    create_govbr_runtime,
)
from govbr_auth.core import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidIdTokenError,
    InvalidStateError,
)
from govbr_auth.core.errors import ProviderRejectedError, ProviderUnavailableError

_AUTHORIZATION_FIELDS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "nonce",
    "code_challenge",
    "code_challenge_method",
)
_TOKEN_FIELDS = ("grant_type", "code", "redirect_uri", "code_verifier")
_AUTHORIZATION_REQUEST_INVALID = "The authorization request is invalid."
_CLIENT_INVALID = "Client authentication failed."
_TOKEN_INVALID = "The access token is invalid or expired."
_TOKEN_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


class _FakeHttpRuntime(Protocol):
    """Expose only the canonical runtime fields required by HTTP routes."""

    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator | None
    prefix: str


@dataclass(frozen=True, slots=True)
class _ProviderRuntimeAdapter:
    """Adapt an advanced supplied provider without composing new resources."""

    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator | None
    prefix: str


def create_fake_govbr_router(
    runtime: FakeGovBrRuntime | FakeGovBrProvider,
    *,
    prefix: str | None = None,
    credential_authenticator: FakeCredentialAuthenticator | None = None,
    automatic_subject: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> APIRouter:
    """Create explicitly mounted fake-provider routes below ``prefix``."""
    runtime = _as_http_runtime(
        runtime,
        prefix=prefix,
        credential_authenticator=credential_authenticator,
    )
    return _build_fake_govbr_routes(
        runtime,
        automatic_subject=automatic_subject,
        clock=clock,
    )


def create_fake_govbr_app(
    runtime: FakeGovBrRuntime | FakeGovBrProvider,
    *,
    credential_authenticator: FakeCredentialAuthenticator | None = None,
    automatic_subject: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Create a standalone ASGI fake provider with routes at the application root."""
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    runtime = _as_http_runtime(
        runtime,
        prefix=None if isinstance(runtime, FakeGovBrRuntime) else "",
        credential_authenticator=credential_authenticator,
    )
    application.include_router(
        _build_fake_govbr_routes(
            runtime,
            automatic_subject=automatic_subject,
            clock=clock,
        )
    )
    return application


def create_fake_app(
    settings: GovBrRuntimeSettings | None = None,
    *,
    clock: Callable[[], datetime] = utc_now,
    user_repository: FakeUserRepository | None = None,
) -> FastAPI:
    """Create the provider-only or complete local fake application profile."""
    resolved_settings = settings or _launcher_settings()
    if resolved_settings.provider is not GovBrProvider.FAKE:
        raise ValueError("fake launcher requires the fake provider")
    if not resolved_settings.fake_end_to_end:
        runtime = create_fake_govbr_runtime(
            resolved_settings,
            clock=clock,
            user_repository=user_repository,
        )
        return create_fake_govbr_app(runtime, clock=clock)

    runtime = create_govbr_runtime(
        resolved_settings,
        fake_transport_factory=lambda fake: _fake_asgi_transport(fake, clock=clock),
        clock=clock,
        user_repository=user_repository,
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
            render_home(credentials=fake_runtime.credentials),
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
    """Run the selected fake profile on its validated loopback endpoint."""
    import uvicorn

    settings = _launcher_settings()
    uvicorn.run(
        "govbr_auth.fake:create_fake_app",
        factory=True,
        host=settings.fake_host,
        port=settings.fake_port,
    )


def _fake_asgi_transport(
    runtime: FakeGovBrRuntime,
    *,
    clock: Callable[[], datetime],
) -> httpx.AsyncBaseTransport:
    """Host the exact mounted provider routes used by the consumer runtime."""
    provider_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    provider_app.include_router(create_fake_govbr_router(runtime, clock=clock))
    return httpx.ASGITransport(app=provider_app)


def _launcher_settings() -> GovBrRuntimeSettings:
    """Default this explicit fake entry point without changing library defaults."""
    environ = dict(os.environ)
    environ.setdefault("GOVBR_PROVIDER", GovBrProvider.FAKE.value)
    return GovBrRuntimeSettings.from_environment(environ)


def _build_fake_govbr_routes(
    runtime: _FakeHttpRuntime,
    *,
    automatic_subject: str | None,
    clock: Callable[[], datetime],
) -> APIRouter:
    provider = runtime.provider
    credential_authenticator = runtime.credential_authenticator
    router = APIRouter(prefix=runtime.prefix)
    login_route_name = f"fake_govbr_login_{id(router):x}"

    @router.get("/authorize")
    async def authorize(request: Request) -> Response:
        values = required_text_values(request.query_params, _AUTHORIZATION_FIELDS)
        if values is None:
            return boundary_error_response(
                "invalid_request",
                _AUTHORIZATION_REQUEST_INVALID,
            )
        authorization_request = FakeAuthorizationRequest(**values)
        try:
            session = provider.begin_authorization(
                authorization_request,
                now=clock(),
            )
            if automatic_subject is not None:
                redirect = provider.complete_authorization(
                    session=session,
                    subject=automatic_subject,
                    now=clock(),
                )
                return RedirectResponse(redirect.redirect_uri, status_code=302)
        except FakeOAuthError as error:
            return oauth_error_response(error)

        login_action = request.url_for(login_route_name).path
        page = (
            render_fake_login(session, login_action=login_action)
            if credential_authenticator is not None
            else render_fake_user_selection(session, login_action=login_action)
        )
        return HTMLResponse(
            page,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/login", name=login_route_name)
    async def login(request: Request) -> Response:
        form = await _read_form(request)
        if credential_authenticator is None:
            values = required_text_values(form, ("request", "subject"))
            if values is None:
                return boundary_error_response(
                    "invalid_request",
                    _AUTHORIZATION_REQUEST_INVALID,
                )
            subject = values["subject"]
        else:
            values = required_text_values(form, ("request", "cpf", "password"))
            if values is None:
                return boundary_error_response(
                    "invalid_request",
                    _AUTHORIZATION_REQUEST_INVALID,
                )
            user = credential_authenticator.authenticate(
                cpf=values["cpf"],
                password=SecretStr(values["password"]),
            )
            if user is None:
                session = FakeAuthorizationSession(
                    request=SecretStr(values["request"]),
                    users=(),
                )
                return HTMLResponse(
                    render_fake_login(
                        session,
                        login_action=request.url_for(login_route_name).path,
                        invalid_credentials=True,
                    ),
                    status_code=401,
                    headers={"Cache-Control": "no-store"},
                )
            subject = user.sub
        session = FakeAuthorizationSession(
            request=SecretStr(values["request"]),
            users=(),
        )
        try:
            redirect = provider.complete_authorization(
                session=session,
                subject=subject,
                now=clock(),
            )
        except FakeOAuthError as error:
            return oauth_error_response(error)
        return RedirectResponse(redirect.redirect_uri, status_code=302)

    @router.post("/token")
    async def token(request: Request) -> Response:
        credentials = parse_basic_authorization(request.headers.get("authorization"))
        if credentials is None:
            return boundary_error_response(
                "invalid_client",
                _CLIENT_INVALID,
                headers=_TOKEN_RESPONSE_HEADERS,
            )
        form = await _read_form(request)
        values = required_text_values(form, _TOKEN_FIELDS)
        if values is None:
            return boundary_error_response(
                "invalid_request",
                _AUTHORIZATION_REQUEST_INVALID,
                headers=_TOKEN_RESPONSE_HEADERS,
            )
        token_request = FakeTokenRequest(
            grant_type=values["grant_type"],
            code=SecretStr(values["code"]),
            redirect_uri=values["redirect_uri"],
            code_verifier=SecretStr(values["code_verifier"]),
        )
        try:
            response = provider.exchange_code(
                credentials=credentials,
                request=token_request,
                now=clock(),
            )
        except FakeOAuthError as error:
            return oauth_error_response(error, extra_headers=_TOKEN_RESPONSE_HEADERS)
        return JSONResponse(
            {
                "access_token": response.access_token.get_secret_value(),
                "token_type": response.token_type,
                "expires_in": response.expires_in,
                "id_token": response.id_token.get_secret_value(),
                "scope": response.scope,
            },
            headers=_TOKEN_RESPONSE_HEADERS,
        )

    @router.get("/jwk")
    async def jwk() -> JSONResponse:
        return JSONResponse(dict(provider.jwks()))

    @router.get("/userinfo")
    async def userinfo(request: Request) -> Response:
        access_token = parse_bearer_authorization(request.headers.get("authorization"))
        if access_token is None:
            return boundary_error_response("invalid_token", _TOKEN_INVALID)
        try:
            user = provider.userinfo(access_token, now=clock())
        except FakeOAuthError as error:
            return oauth_error_response(error)
        return JSONResponse(user.model_dump(exclude_none=True, mode="json"))

    return router


def _as_http_runtime(
    runtime: FakeGovBrRuntime | FakeGovBrProvider,
    *,
    prefix: str | None,
    credential_authenticator: FakeCredentialAuthenticator | None,
) -> _FakeHttpRuntime:
    if isinstance(runtime, FakeGovBrRuntime):
        if prefix is not None and prefix != runtime.prefix:
            raise ValueError("prefix does not match runtime prefix")

        return _ProviderRuntimeAdapter(
            provider=runtime.provider,
            credential_authenticator=(
                runtime.credential_authenticator
                if credential_authenticator is None
                else credential_authenticator
            ),
            prefix=runtime.prefix,
        )
    return _ProviderRuntimeAdapter(
        provider=runtime,
        credential_authenticator=credential_authenticator,
        prefix="/fake-govbr" if prefix is None else prefix,
    )


async def _read_form(request: Request) -> FormData:
    try:
        return await request.form()
    except (MultiPartException, UnicodeDecodeError, ValueError):
        return FormData()
