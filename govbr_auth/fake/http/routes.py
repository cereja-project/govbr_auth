"""FastAPI route registration for the local Fake Gov.br provider."""

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException

from govbr_auth.fake._html import render_fake_login
from govbr_auth.fake.http.application import (
    FakeGovHttpApplication,
    FakeHttpRuntime,
    resolve_fake_http_application,
)
from govbr_auth.fake.http.responses import boundary_error_response, oauth_error_response
from govbr_auth.fake.provider import FakeOAuthError

_TOKEN_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


def build_fake_govbr_routes(
    runtime: FakeHttpRuntime,
    *,
    automatic_subject: str | None,
    clock: Callable[[], datetime],
    application: FakeGovHttpApplication | None = None,
) -> APIRouter:
    """Build the five protocol routes from a narrow runtime view."""
    if application is None:
        application = resolve_fake_http_application(runtime, clock=clock)
    router = APIRouter(prefix=runtime.prefix)
    login_route_name = f"fake_govbr_login_{id(router):x}"

    @router.get("/authorize")
    async def authorize(request: Request) -> Response:
        try:
            result = application.authorize(
                request.query_params,
                automatic_subject=automatic_subject,
            )
        except FakeOAuthError as error:
            return oauth_error_response(error)
        if result.redirect is not None:
            return RedirectResponse(result.redirect.redirect_uri, status_code=302)

        login_action = request.url_for(login_route_name).path
        return HTMLResponse(
            render_fake_login(result.session, login_action=login_action),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/login", name=login_route_name)
    async def login(request: Request) -> Response:
        form = await _read_form(request)
        try:
            result = application.login(form)
        except FakeOAuthError as error:
            return oauth_error_response(error)
        if result.invalid_credentials:
            return HTMLResponse(
                render_fake_login(
                    result.session,
                    login_action=request.url_for(login_route_name).path,
                    invalid_credentials=True,
                ),
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        if result.redirect is None:
            raise RuntimeError("successful fake login must include a redirect")
        return RedirectResponse(result.redirect.redirect_uri, status_code=302)

    @router.post("/token")
    async def token(request: Request) -> Response:
        try:
            credentials = application.parse_client_credentials(
                request.headers.get("authorization")
            )
        except FakeOAuthError as error:
            return oauth_error_response(error, extra_headers=_TOKEN_RESPONSE_HEADERS)
        form = await _read_form(request)
        try:
            response = application.token(credentials, form)
        except FakeOAuthError as error:
            return boundary_error_response(
                error.error,
                error.description,
                headers=_TOKEN_RESPONSE_HEADERS,
            )
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
        return JSONResponse(dict(application.jwks()))

    @router.get("/userinfo")
    async def userinfo(request: Request) -> Response:
        try:
            user = application.userinfo(request.headers.get("authorization"))
        except FakeOAuthError as error:
            return oauth_error_response(error)
        return JSONResponse(user.model_dump(exclude_none=True, mode="json"))

    @router.get("/logout")
    async def logout(request: Request) -> Response:
        try:
            redirect_uri = application.logout(
                request.query_params.get("post_logout_redirect_uri")
            )
        except FakeOAuthError as error:
            return oauth_error_response(error)
        return RedirectResponse(redirect_uri, status_code=302)

    return router


async def _read_form(request: Request) -> FormData:
    try:
        return await request.form()
    except (MultiPartException, UnicodeDecodeError, ValueError):
        return FormData()
