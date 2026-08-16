"""Explicit FastAPI and ASGI factories for the local Fake Gov.br provider."""

import base64
import binascii
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import SecretStr
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException

from govbr_auth.fake._html import render_fake_login, render_fake_user_selection
from govbr_auth.fake.credentials import FakeCredentialAuthenticator
from govbr_auth.fake.provider import (
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeGovBrProvider,
    FakeOAuthError,
    FakeTokenRequest,
)
from govbr_auth.fake.runtime import FakeGovBrRuntime
from govbr_auth.fastapi import utc_now

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
        prefix="",
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
        values = _required_text_values(request.query_params, _AUTHORIZATION_FIELDS)
        if values is None:
            return _boundary_error_response(
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
            return _oauth_error_response(error)

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
            values = _required_text_values(form, ("request", "subject"))
            if values is None:
                return _boundary_error_response(
                    "invalid_request",
                    _AUTHORIZATION_REQUEST_INVALID,
                )
            subject = values["subject"]
        else:
            values = _required_text_values(form, ("request", "cpf", "password"))
            if values is None:
                return _boundary_error_response(
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
            return _oauth_error_response(error)
        return RedirectResponse(redirect.redirect_uri, status_code=302)

    @router.post("/token")
    async def token(request: Request) -> Response:
        credentials = _parse_basic_authorization(request.headers.get("authorization"))
        if credentials is None:
            return _boundary_error_response("invalid_client", _CLIENT_INVALID)
        form = await _read_form(request)
        values = _required_text_values(form, _TOKEN_FIELDS)
        if values is None:
            return _boundary_error_response(
                "invalid_request",
                _AUTHORIZATION_REQUEST_INVALID,
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
            return _oauth_error_response(error)
        return JSONResponse(
            {
                "access_token": response.access_token.get_secret_value(),
                "token_type": response.token_type,
                "expires_in": response.expires_in,
                "id_token": response.id_token.get_secret_value(),
                "scope": response.scope,
            }
        )

    @router.get("/jwk")
    async def jwk() -> JSONResponse:
        return JSONResponse(dict(provider.jwks()))

    @router.get("/userinfo")
    async def userinfo(request: Request) -> Response:
        access_token = _parse_bearer_authorization(request.headers.get("authorization"))
        if access_token is None:
            return _boundary_error_response("invalid_token", _TOKEN_INVALID)
        try:
            user = provider.userinfo(access_token, now=clock())
        except FakeOAuthError as error:
            return _oauth_error_response(error)
        return JSONResponse(user.model_dump(exclude_none=True, mode="json"))

    return router


def _as_http_runtime(
    runtime: FakeGovBrRuntime | FakeGovBrProvider,
    *,
    prefix: str | None,
    credential_authenticator: FakeCredentialAuthenticator | None,
) -> _FakeHttpRuntime:
    if isinstance(runtime, FakeGovBrRuntime):
        return _ProviderRuntimeAdapter(
            provider=runtime.provider,
            credential_authenticator=(
                runtime.credential_authenticator
                if credential_authenticator is None
                else credential_authenticator
            ),
            prefix=runtime.prefix if prefix is None else prefix,
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


def _required_text_values(
    values: Mapping[str, object],
    names: tuple[str, ...],
) -> dict[str, str] | None:
    parsed: dict[str, str] = {}
    for name in names:
        value = values.get(name)
        if not isinstance(value, str) or not value.strip():
            return None
        parsed[name] = value
    return parsed


def _parse_basic_authorization(value: str | None) -> FakeClientCredentials | None:
    encoded = _parse_authorization_scheme(value, scheme="Basic")
    if encoded is None:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    client_id, separator, client_secret = decoded.partition(":")
    if not separator or not client_id.strip() or not client_secret.strip():
        return None
    return FakeClientCredentials(
        client_id=client_id,
        client_secret=SecretStr(client_secret),
    )


def _parse_bearer_authorization(value: str | None) -> SecretStr | None:
    token = _parse_authorization_scheme(value, scheme="Bearer")
    if token is None or any(character.isspace() for character in token):
        return None
    return SecretStr(token)


def _parse_authorization_scheme(value: str | None, *, scheme: str) -> str | None:
    if value is None or len(value) > 8192:
        return None
    parsed_scheme, separator, credentials = value.partition(" ")
    if (
        not separator
        or parsed_scheme.casefold() != scheme.casefold()
        or not credentials
        or credentials != credentials.strip()
    ):
        return None
    return credentials


def _boundary_error_response(error: str, description: str) -> JSONResponse:
    return _oauth_error_response(FakeOAuthError(error=error, description=description))


def _oauth_error_response(error: FakeOAuthError) -> JSONResponse:
    status_code = 400
    headers = None
    if error.error == "invalid_client":
        status_code = 401
        headers = {"WWW-Authenticate": 'Basic realm="fake-govbr"'}
    elif error.error == "invalid_token":
        status_code = 401
        headers = {"WWW-Authenticate": "Bearer"}
    elif error.error == "access_denied":
        status_code = 403
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error.error,
            "error_description": error.description,
        },
        headers=headers,
    )
