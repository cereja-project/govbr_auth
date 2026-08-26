"""Framework-neutral public error descriptions for consumer adapters."""

from dataclasses import dataclass

from govbr_auth.core.errors import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidStateError,
    ProviderRejectedError,
    ProviderUnavailableError,
)

INVALID_CALLBACK_MESSAGE = "Callback parameters are invalid."


@dataclass(frozen=True, slots=True)
class AuthErrorDescription:
    """Stable public status and message selected for one internal error."""

    status_code: int
    message: str


def describe_auth_error(error: GovBrAuthError) -> AuthErrorDescription:
    """Map internal authentication failures to a safe public description."""
    if isinstance(error, (InvalidStateError, ExpiredTransactionError)):
        return AuthErrorDescription(
            status_code=400,
            message="The authorization request is invalid or expired.",
        )
    if isinstance(error, ProviderRejectedError):
        return AuthErrorDescription(
            status_code=502,
            message="Gov.br rejected the request.",
        )
    if isinstance(error, ProviderUnavailableError):
        return AuthErrorDescription(
            status_code=503,
            message="Gov.br is temporarily unavailable.",
        )
    return AuthErrorDescription(
        status_code=502,
        message="Gov.br authentication failed.",
    )
