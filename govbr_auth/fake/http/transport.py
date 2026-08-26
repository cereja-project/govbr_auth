"""Framework-neutral in-process transport for FakeGov consumer calls."""

from collections.abc import Callable
from datetime import datetime
from urllib.parse import parse_qs

import httpx

from govbr_auth.fake.http.application import (
    FakeHttpRuntime,
    resolve_fake_http_application,
)
from govbr_auth.fake.provider import FakeOAuthError

_TOKEN_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


class FakeGovHttpTransport(httpx.AsyncBaseTransport):
    """Serve FakeGov protocol calls without importing a web framework."""

    def __init__(
        self,
        runtime: FakeHttpRuntime,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._prefix = runtime.prefix.rstrip("/")
        self._application = resolve_fake_http_application(runtime, clock=clock)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.removeprefix(self._prefix)
        try:
            if endpoint == "/token" and request.method == "POST":
                credentials = self._application.parse_client_credentials(
                    request.headers.get("authorization")
                )
                response = self._application.token(
                    credentials,
                    _form_values(request),
                )
                return httpx.Response(
                    200,
                    json={
                        "access_token": response.access_token.get_secret_value(),
                        "token_type": response.token_type,
                        "expires_in": response.expires_in,
                        "id_token": response.id_token.get_secret_value(),
                        "scope": response.scope,
                    },
                    headers=_TOKEN_HEADERS,
                    request=request,
                )
            if endpoint == "/jwk" and request.method == "GET":
                return httpx.Response(
                    200, json=dict(self._application.jwks()), request=request
                )
            if endpoint == "/userinfo" and request.method == "GET":
                user = self._application.userinfo(request.headers.get("authorization"))
                return httpx.Response(
                    200,
                    json=user.model_dump(exclude_none=True, mode="json"),
                    request=request,
                )
            return httpx.Response(404, json={"detail": "Not Found"}, request=request)
        except FakeOAuthError as error:
            return _oauth_error_response(error, request=request)


def _form_values(request: httpx.Request) -> dict[str, str]:
    try:
        body = request.content.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return {}
    return {name: values[0] for name, values in parse_qs(body).items() if values}


def _oauth_error_response(
    error: FakeOAuthError,
    *,
    request: httpx.Request,
) -> httpx.Response:
    status_code = 400
    headers: dict[str, str] = {}
    if error.error == "invalid_client":
        status_code = 401
        headers.update(
            _TOKEN_HEADERS, **{"WWW-Authenticate": 'Basic realm="fake-govbr"'}
        )
    elif error.error == "invalid_token":
        status_code = 401
        headers["WWW-Authenticate"] = "Bearer"
    elif error.error == "access_denied":
        status_code = 403
    if request.url.path.endswith("/token"):
        headers.update(_TOKEN_HEADERS)
    return httpx.Response(
        status_code,
        json={"error": error.error, "error_description": error.description},
        headers=headers,
        request=request,
    )
