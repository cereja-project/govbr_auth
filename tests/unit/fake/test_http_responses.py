"""Unit tests for FakeGov OAuth response mapping."""

from govbr_auth.fake.provider import FakeOAuthError
from govbr_auth.fake.http.responses import (
    boundary_error_response,
    oauth_error_response,
)


def test_boundary_error_response_returns_oauth_error_payload() -> None:
    response = boundary_error_response("invalid_request", "Request is invalid.")

    assert response.status_code == 400
    assert response.body == (
        b'{"error":"invalid_request","error_description":"Request is invalid."}'
    )
    assert response.headers["content-type"] == "application/json"


def test_oauth_error_response_maps_authentication_headers_and_status() -> None:
    response = oauth_error_response(
        FakeOAuthError(error="invalid_client", description="Client is invalid."),
        extra_headers={"Cache-Control": "no-store"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="fake-govbr"'
    assert response.headers["cache-control"] == "no-store"
    assert response.body == (
        b'{"error":"invalid_client","error_description":"Client is invalid."}'
    )
    assert b"client_secret" not in response.body
    assert b"access_token" not in response.body
    assert b"id_token" not in response.body


def test_oauth_error_response_maps_access_denied() -> None:
    response = oauth_error_response(
        FakeOAuthError(error="access_denied", description="Access denied.")
    )

    assert response.status_code == 403
    assert response.body == (
        b'{"error":"access_denied","error_description":"Access denied."}'
    )
