"""Tests for the shared public authentication-error policy."""

import pytest

from govbr_auth.adapters._errors import describe_auth_error
from govbr_auth.core.errors import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidStateError,
    ProviderRejectedError,
    ProviderUnavailableError,
)


@pytest.mark.parametrize(
    ("error", "status_code", "message"),
    (
        (
            InvalidStateError("internal state"),
            400,
            "The authorization request is invalid or expired.",
        ),
        (
            ExpiredTransactionError("internal expiry"),
            400,
            "The authorization request is invalid or expired.",
        ),
        (
            ProviderRejectedError("secret provider detail"),
            502,
            "Gov.br rejected the request.",
        ),
        (
            ProviderUnavailableError("secret transport detail"),
            503,
            "Gov.br is temporarily unavailable.",
        ),
        (
            GovBrAuthError("secret fallback detail"),
            502,
            "Gov.br authentication failed.",
        ),
    ),
)
def test_error_policy_exposes_only_stable_public_data(
    error: GovBrAuthError,
    status_code: int,
    message: str,
) -> None:
    description = describe_auth_error(error)

    assert description.status_code == status_code
    assert description.message == message
    assert "secret" not in description.message
