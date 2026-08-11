"""Stable exception types for the new Gov.br OAuth core."""


class GovBrAuthError(Exception):
    """Represent a Gov.br authentication failure with a stable error code."""

    code: str = "govbr_auth_error"


class InvalidStateError(GovBrAuthError):
    """Represent a rejected OAuth state value."""

    code: str = "invalid_state"


class ExpiredTransactionError(GovBrAuthError):
    """Represent an OAuth transaction that has expired."""

    code: str = "expired_transaction"


class InvalidIdTokenError(GovBrAuthError):
    """Represent a rejected OpenID Connect ID token."""

    code: str = "invalid_id_token"
