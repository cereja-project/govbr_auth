"""Stateless protection for short-lived OAuth transactions."""

import json
import secrets
from datetime import datetime, timedelta
from typing import Literal, Protocol

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from govbr_auth.core.errors import ExpiredTransactionError, InvalidStateError
from govbr_auth.core.models import AuthTransaction

_INVALID_STATE_MESSAGE = "OAuth state is invalid"
_EXPIRED_TRANSACTION_MESSAGE = "OAuth transaction has expired"
_INVALID_SECRET_MESSAGE = (
    "transaction secret must be a URL-safe base64-encoded 32-byte Fernet key; "
    "generate one with govbr_auth.generate_transaction_secret()"
)


class _TransactionEnvelope(BaseModel):
    """Validate the private versioned representation carried by OAuth state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    transaction: AuthTransaction


def generate_transaction_secret() -> str:
    """Generate a URL-safe Fernet key for protecting OAuth transactions."""
    return Fernet.generate_key().decode("ascii")


class TransactionCodec(Protocol):
    """Define stateless OAuth transaction protection operations."""

    def issue(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        """Create and protect a new OAuth transaction."""
        ...

    def decode(self, state: str, *, now: datetime) -> AuthTransaction:
        """Authenticate and decode an OAuth transaction."""
        ...


class EncryptedTransactionCodec:
    """Protect OAuth transactions without retaining process-local state."""

    def __init__(
        self,
        secret: SecretStr,
        ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        secret_value = secret.get_secret_value()
        if not secret_value.strip():
            raise ValueError("secret must not be empty")
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")

        self._fernet = self._create_fernet(secret_value)
        self._ttl = ttl

    def issue(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        """Create and protect a new OAuth transaction."""
        self._require_timezone_aware(now)
        transaction = AuthTransaction(
            transaction_id=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            nonce=secrets.token_urlsafe(32),
            issued_at=now,
            expires_at=now + self._ttl,
        )
        transaction_payload = {
            "transaction_id": transaction.transaction_id,
            "code_verifier": transaction.code_verifier.get_secret_value(),
            "nonce": transaction.nonce.get_secret_value(),
            "issued_at": transaction.issued_at.isoformat(),
            "expires_at": transaction.expires_at.isoformat(),
        }
        payload = json.dumps(
            {"transaction": transaction_payload, "version": 1},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        state = self._fernet.encrypt(payload).decode("ascii")
        return state, transaction

    def decode(self, state: str, *, now: datetime) -> AuthTransaction:
        """Authenticate and decode an OAuth transaction."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        try:
            payload = self._fernet.decrypt(state.encode("ascii"))
            transaction = _TransactionEnvelope.model_validate_json(payload).transaction
        except (InvalidToken, UnicodeEncodeError, ValidationError) as error:
            failure_type = type(error).__name__

        else:
            if transaction.issued_at > now:
                safe_cause = ValueError(
                    "OAuth state validation failed (FutureIssuedAt)"
                )
                raise InvalidStateError(_INVALID_STATE_MESSAGE) from safe_cause
            if now >= transaction.expires_at:
                raise ExpiredTransactionError(_EXPIRED_TRANSACTION_MESSAGE)
            return transaction

        safe_cause = ValueError(f"OAuth state validation failed ({failure_type})")
        raise InvalidStateError(_INVALID_STATE_MESSAGE) from safe_cause

    @staticmethod
    def _create_fernet(secret_value: str) -> Fernet:
        try:
            return Fernet(secret_value.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as error:
            failure_type = type(error).__name__

        safe_cause = ValueError(f"Fernet key validation failed ({failure_type})")
        raise ValueError(_INVALID_SECRET_MESSAGE) from safe_cause

    @staticmethod
    def _require_timezone_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
