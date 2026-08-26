"""Native Django routes for the local FakeGov provider."""

from collections.abc import Callable
from datetime import datetime

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import URLPattern, path
from django.views.decorators.csrf import csrf_exempt

from govbr_auth.fake._html import render_fake_login, render_fake_user_selection
from govbr_auth.fake.http.application import (
    FakeGovHttpApplication,
    FakeHttpRuntime,
    resolve_fake_http_application,
)
from govbr_auth.fake.provider import FakeOAuthError

_TOKEN_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def create_fake_govbr_urlpatterns(
    runtime: FakeHttpRuntime,
    *,
    clock: Callable[[], datetime],
    application: FakeGovHttpApplication | None = None,
) -> list[URLPattern]:
    """Create Django provider routes from the neutral FakeGov application."""
    if application is None:
        application = resolve_fake_http_application(runtime, clock=clock)
    prefix = runtime.prefix.strip("/")

    def authorize(request: HttpRequest) -> HttpResponse:
        try:
            result = application.authorize(request.GET)
        except FakeOAuthError as error:
            return _oauth_error(error)
        if result.redirect is not None:
            return HttpResponseRedirect(result.redirect.redirect_uri)
        login_action = f"/{prefix}/login" if prefix else "/login"
        if runtime.credential_authenticator is not None:
            body = render_fake_login(result.session, login_action=login_action)
        else:
            body = render_fake_user_selection(result.session, login_action=login_action)
        return HttpResponse(body, headers={"Cache-Control": "no-store"})

    @csrf_exempt
    def login(request: HttpRequest) -> HttpResponse:
        try:
            result = application.login(request.POST)
        except FakeOAuthError as error:
            return _oauth_error(error)
        if result.invalid_credentials:
            return HttpResponse(
                render_fake_login(
                    result.session,
                    login_action=request.path,
                    invalid_credentials=True,
                ),
                status=401,
                headers={"Cache-Control": "no-store"},
            )
        if result.redirect is None:
            raise RuntimeError("successful fake login must include a redirect")
        return HttpResponseRedirect(result.redirect.redirect_uri)

    @csrf_exempt
    def token(request: HttpRequest) -> JsonResponse:
        try:
            credentials = application.parse_client_credentials(
                request.headers.get("Authorization")
            )
            response = application.token(credentials, request.POST)
        except FakeOAuthError as error:
            return _oauth_error(error, token_response=True)
        return JsonResponse(
            {
                "access_token": response.access_token.get_secret_value(),
                "token_type": response.token_type,
                "expires_in": response.expires_in,
                "id_token": response.id_token.get_secret_value(),
                "scope": response.scope,
            },
            headers=_TOKEN_HEADERS,
        )

    def jwk(request: HttpRequest) -> JsonResponse:
        return JsonResponse(dict(application.jwks()))

    def userinfo(request: HttpRequest) -> JsonResponse:
        try:
            user = application.userinfo(request.headers.get("Authorization"))
        except FakeOAuthError as error:
            return _oauth_error(error)
        return JsonResponse(user.model_dump(exclude_none=True, mode="json"))

    return [
        path(f"{prefix}/authorize" if prefix else "authorize", authorize),
        path(f"{prefix}/login" if prefix else "login", login),
        path(f"{prefix}/token" if prefix else "token", token),
        path(f"{prefix}/jwk" if prefix else "jwk", jwk),
        path(f"{prefix}/userinfo" if prefix else "userinfo", userinfo),
    ]


def _oauth_error(
    error: FakeOAuthError, *, token_response: bool = False
) -> JsonResponse:
    status_code = 400
    headers = dict(_TOKEN_HEADERS) if token_response else {}
    if error.error == "invalid_client":
        status_code = 401
        headers["WWW-Authenticate"] = 'Basic realm="fake-govbr"'
    elif error.error == "invalid_token":
        status_code = 401
        headers["WWW-Authenticate"] = "Bearer"
    elif error.error == "access_denied":
        status_code = 403
    return JsonResponse(
        {"error": error.error, "error_description": error.description},
        status=status_code,
        headers=headers,
    )
