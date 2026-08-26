"""Unit tests for FakeGov HTTP boundary parsers."""

from pydantic import SecretStr

from govbr_auth.fake.http.parsing import (
    parse_basic_authorization,
    parse_bearer_authorization,
    required_text_values,
)


def test_required_text_values_returns_only_nonempty_strings() -> None:
    assert required_text_values(
        {"request": " opaque ", "subject": "123"},
        ("request", "subject"),
    ) == {"request": " opaque ", "subject": "123"}


def test_required_text_values_rejects_missing_or_blank_values() -> None:
    assert required_text_values({"request": "opaque"}, ("request", "subject")) is None
    assert (
        required_text_values(
            {"request": "opaque", "subject": "   "},
            ("request", "subject"),
        )
        is None
    )


def test_parse_basic_authorization_returns_client_credentials() -> None:
    credentials = parse_basic_authorization("Basic ZGVtby1pZDpzZWNyZXQ=")

    assert credentials is not None
    assert credentials.client_id == "demo-id"
    assert credentials.client_secret == SecretStr("secret")


def test_parse_basic_authorization_rejects_malformed_values() -> None:
    assert parse_basic_authorization("Bearer token") is None
    assert parse_basic_authorization("Basic !!!") is None
    assert parse_basic_authorization(None) is None


def test_parse_bearer_authorization_returns_secret_token() -> None:
    token = parse_bearer_authorization("Bearer opaque-token")

    assert token == SecretStr("opaque-token")


def test_parse_bearer_authorization_rejects_whitespace_and_wrong_scheme() -> None:
    assert parse_bearer_authorization("Basic opaque-token") is None
    assert parse_bearer_authorization("Bearer opaque token") is None
    assert parse_bearer_authorization("Bearer ") is None
