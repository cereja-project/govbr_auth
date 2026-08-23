"""FastAPI route registration for the local Fake Gov.br provider."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import SecretStr
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException

from govbr_auth.fake._html import render_fake_login, render_fake_user_selection
from govbr_auth.fake.credentials import FakeCredentialAuthenticator
from govbr_auth.fake.http.parsing import (
    parse_basic_authorization,
    parse_bearer_authorization,
    required_text_values,
)
from govbr_auth.fake.http.responses import boundary_error_response, oauth_error_response
from govbr_auth.fake.provider import (
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeGovBrProvider,
    FakeOAuthError,
    FakeTokenRequest,
)

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


class FakeHttpRuntime(Protocol):
    """Expose only the canonical runtime fields required by HTTP routes."""

    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator | None
    prefix: str


def build_fake_govbr_routes(
    runtime: FakeHttpRuntime,
    *,
    automatic_subject: str | None,
    clock: Callable[[], datetime],
) -> APIRouter:
    """Build the five protocol routes from a narrow runtime view."""
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


async def _read_form(request: Request) -> FormData:
    try:
        return await request.form()
    except (MultiPartException, UnicodeDecodeError, ValueError):
        return FormData()
