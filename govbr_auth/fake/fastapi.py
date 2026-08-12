"""Explicit FastAPI and ASGI factories for the local Fake Gov.br provider."""

import base64
import binascii
import html
from collections.abc import Callable, Mapping
from datetime import datetime

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import SecretStr
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException

from govbr_auth.fake.provider import (
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeGovBrProvider,
    FakeOAuthError,
    FakeTokenRequest,
)
from govbr_auth.fake.models import FakeUser
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


def create_fake_govbr_router(
    provider: FakeGovBrProvider,
    *,
    prefix: str = "/fake-govbr",
    automatic_subject: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> APIRouter:
    """Create explicitly mounted fake-provider routes below ``prefix``."""
    return _build_fake_govbr_routes(
        provider,
        prefix=prefix,
        automatic_subject=automatic_subject,
        clock=clock,
    )


def create_fake_govbr_app(
    provider: FakeGovBrProvider,
    *,
    automatic_subject: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Create a standalone ASGI fake provider with routes at the application root."""
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    application.include_router(
        _build_fake_govbr_routes(
            provider,
            prefix="",
            automatic_subject=automatic_subject,
            clock=clock,
        )
    )
    return application


def _build_fake_govbr_routes(
    provider: FakeGovBrProvider,
    *,
    prefix: str,
    automatic_subject: str | None,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix=prefix)
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

        return HTMLResponse(
            _render_login_page(
                session,
                login_action=request.url_for(login_route_name).path,
            ),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/login", name=login_route_name)
    async def login(request: Request) -> Response:
        form = await _read_form(request)
        values = _required_text_values(form, ("request", "subject"))
        if values is None:
            return _boundary_error_response(
                "invalid_request",
                _AUTHORIZATION_REQUEST_INVALID,
            )
        session = FakeAuthorizationSession(
            request=SecretStr(values["request"]),
            users=(),
        )
        try:
            redirect = provider.complete_authorization(
                session=session,
                subject=values["subject"],
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


def _render_login_page(
    session: FakeAuthorizationSession,
    *,
    login_action: str,
) -> str:
    request_value = html.escape(session.request.get_secret_value(), quote=True)
    action_value = html.escape(login_action, quote=True)
    choices = "".join(_render_user_choice(user) for user in session.users)
    return (
        "<!doctype html>"
        '<html lang="pt-BR"><head><meta charset="utf-8">'
        "<title>FAKE / SIMULAÇÃO</title></head><body>"
        "<h1>FAKE / SIMULAÇÃO</h1>"
        "<p>Provedor local de teste. Não é o portal oficial.</p>"
        f'<form method="post" action="{action_value}">'
        f'<input type="hidden" name="request" value="{request_value}">'
        f"{choices}</form></body></html>"
    )


def _render_user_choice(user: FakeUser) -> str:
    subject = html.escape(user.sub, quote=True)
    label_value = user.name or user.preferred_username or user.sub
    label = html.escape(label_value, quote=True)
    return (
        f'<button type="submit" name="subject" value="{subject}">'
        f"{label} ({subject})</button>"
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
