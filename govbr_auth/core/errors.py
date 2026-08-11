"""Stable exception types for the new Gov.br OAuth core."""


class GovBrAuthError(Exception):
    """Represent a Gov.br authentication failure with a stable error code."""

    code = "govbr_auth_error"


class InvalidStateError(GovBrAuthError):
    """Represent a rejected OAuth state value."""

    code = "invalid_state"


class ExpiredTransactionError(GovBrAuthError):
    """Represent an OAuth transaction that has expired."""

    code = "expired_transaction"


class InvalidIdTokenError(GovBrAuthError):
    """Represent a rejected OpenID Connect ID token."""

    code = "invalid_id_token"
