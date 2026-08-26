"""Native Flask routes for the local FakeGov provider."""

from collections.abc import Callable
from datetime import datetime

from flask import Blueprint, Response, jsonify, redirect, request

from govbr_auth.fake._html import render_fake_login, render_fake_user_selection
from govbr_auth.fake.http.application import (
    FakeGovHttpApplication,
    FakeHttpRuntime,
    resolve_fake_http_application,
)
from govbr_auth.fake.provider import FakeOAuthError

_TOKEN_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def create_fake_govbr_blueprint(
    runtime: FakeHttpRuntime,
    *,
    clock: Callable[[], datetime],
    application: FakeGovHttpApplication | None = None,
) -> Blueprint:
    """Create a Flask provider blueprint from the neutral FakeGov application."""
    if application is None:
        application = resolve_fake_http_application(runtime, clock=clock)
    blueprint = Blueprint("fake_govbr", __name__, url_prefix=runtime.prefix or "")

    @blueprint.get("/authorize")
    def authorize():
        try:
            result = application.authorize(request.args)
        except FakeOAuthError as error:
            return _oauth_error(error)
        if result.redirect is not None:
            return redirect(result.redirect.redirect_uri)
        login_action = f"{runtime.prefix}/login" if runtime.prefix else "/login"
        if runtime.credential_authenticator is not None:
            body = render_fake_login(result.session, login_action=login_action)
        else:
            body = render_fake_user_selection(result.session, login_action=login_action)
        return Response(body, headers={"Cache-Control": "no-store"})

    @blueprint.post("/login")
    def login():
        try:
            result = application.login(request.form)
        except FakeOAuthError as error:
            return _oauth_error(error)
        if result.invalid_credentials:
            return Response(
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
        return redirect(result.redirect.redirect_uri)

    @blueprint.post("/token")
    def token():
        try:
            credentials = application.parse_client_credentials(
                request.headers.get("Authorization")
            )
            token_response = application.token(credentials, request.form)
        except FakeOAuthError as error:
            return _oauth_error(error, token_response=True)
        response = jsonify(
            {
                "access_token": token_response.access_token.get_secret_value(),
                "token_type": token_response.token_type,
                "expires_in": token_response.expires_in,
                "id_token": token_response.id_token.get_secret_value(),
                "scope": token_response.scope,
            }
        )
        response.headers.update(_TOKEN_HEADERS)
        return response

    @blueprint.get("/jwk")
    def jwk():
        return jsonify(dict(application.jwks()))

    @blueprint.get("/userinfo")
    def userinfo():
        try:
            user = application.userinfo(request.headers.get("Authorization"))
        except FakeOAuthError as error:
            return _oauth_error(error)
        return jsonify(user.model_dump(exclude_none=True, mode="json"))

    return blueprint


def _oauth_error(error: FakeOAuthError, *, token_response: bool = False):
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
    response = jsonify({"error": error.error, "error_description": error.description})
    response.status_code = status_code
    response.headers.update(headers)
    return response
