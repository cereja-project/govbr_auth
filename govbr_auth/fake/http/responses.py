"""OAuth response mapping for the FakeGov HTTP adapter."""

from collections.abc import Mapping

from fastapi.responses import JSONResponse

from govbr_auth.fake.provider import FakeOAuthError


def boundary_error_response(
    error: str,
    description: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a protocol error response for malformed HTTP input."""
    return oauth_error_response(
        FakeOAuthError(error=error, description=description),
        extra_headers=headers,
    )


def oauth_error_response(
    error: FakeOAuthError,
    *,
    extra_headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Translate one fake-provider OAuth error to its HTTP response."""
    status_code = 400
    response_headers = dict(extra_headers or {})
    if error.error == "invalid_client":
        status_code = 401
        response_headers["WWW-Authenticate"] = 'Basic realm="fake-govbr"'
    elif error.error == "invalid_token":
        status_code = 401
        response_headers["WWW-Authenticate"] = "Bearer"
    elif error.error == "access_denied":
        status_code = 403
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error.error,
            "error_description": error.description,
        },
        headers=response_headers,
    )
