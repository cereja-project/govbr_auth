"""Tests for immutable OAuth domain models and errors."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from govbr_auth.core.errors import ExpiredTransactionError, GovBrAuthError, InvalidIdTokenError, InvalidStateError
from govbr_auth.core.models import AuthTransaction, GovBrAddress, GovBrUser, TokenSet


def test_auth_transaction_is_immutable() -> None:
    issued_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    transaction = AuthTransaction(
        transaction_id="transaction-123",
        code_verifier="verifier-secret",
        nonce="nonce-secret",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=5),
    )

    with pytest.raises(ValidationError, match="frozen"):
        transaction.transaction_id = "another-transaction"


def test_auth_transaction_rejects_expiration_before_issuance() -> None:
    issued_at = datetime(2026, 8, 11, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="expires_at"):
        AuthTransaction(
            transaction_id="transaction-123",
            code_verifier="verifier-secret",
            nonce="nonce-secret",
            issued_at=issued_at,
            expires_at=issued_at - timedelta(seconds=1),
        )


def test_auth_transaction_rejects_naive_datetimes() -> None:
    issued_at = datetime(2026, 8, 11)

    with pytest.raises(ValidationError, match="timezone-aware"):
        AuthTransaction(
            transaction_id="transaction-123",
            code_verifier="verifier-secret",
            nonce="nonce-secret",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=5),
        )


@pytest.mark.parametrize(
    "field_name",
    [
        pytest.param("transaction_id", id="blank_transaction_id"),
        pytest.param("code_verifier", id="blank_code_verifier"),
        pytest.param("nonce", id="blank_nonce"),
    ],
)
def test_auth_transaction_rejects_blank_security_values(field_name: str) -> None:
    issued_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    transaction_data = {
        "transaction_id": "transaction-123",
        "code_verifier": "verifier-secret",
        "nonce": "nonce-secret",
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(minutes=5),
    }
    transaction_data[field_name] = "   "

    with pytest.raises(ValidationError, match="must not be empty"):
        AuthTransaction(**transaction_data)


def test_token_set_requires_bearer_tokens() -> None:
    with pytest.raises(ValidationError, match="Bearer"):
        TokenSet(
            access_token="access-token",
            id_token="id-token",
            token_type="MAC",
            expires_in=300,
            scope="openid profile email",
        )


@pytest.mark.parametrize(
    "field_name",
    [
        pytest.param("access_token", id="blank_access_token"),
        pytest.param("id_token", id="blank_id_token"),
        pytest.param("scope", id="blank_scope"),
    ],
)
def test_token_set_rejects_blank_security_values(field_name: str) -> None:
    token_data = {
        "access_token": "access-token",
        "id_token": "id-token",
        "token_type": "Bearer",
        "expires_in": 300,
        "scope": "openid profile email",
    }
    token_data[field_name] = "   "

    with pytest.raises(ValidationError, match="must not be empty"):
        TokenSet(**token_data)


def test_govbr_user_rejects_unknown_claims() -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        GovBrUser(sub="subject-123", unexpected="claim")


def test_govbr_user_rejects_blank_subject() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        GovBrUser(sub="   ")


def test_govbr_user_address_is_immutable() -> None:
    user = GovBrUser(sub="subject-123", address={"country": "BR"})
    address = user.address

    assert isinstance(address, GovBrAddress)

    with pytest.raises(ValidationError, match="frozen"):
        address.country = "AR"


@pytest.mark.parametrize(
    ("error_type", "expected_code"),
    [
        pytest.param(InvalidStateError, "invalid_state", id="invalid_state"),
        pytest.param(ExpiredTransactionError, "expired_transaction", id="expired_transaction"),
        pytest.param(InvalidIdTokenError, "invalid_id_token", id="invalid_id_token"),
    ],
)
def test_auth_errors_expose_stable_code(error_type: type[GovBrAuthError], expected_code: str) -> None:
    error = error_type("test failure")

    assert error.code == expected_code
