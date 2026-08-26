"""Protected in-memory storage for short-lived OAuth transactions."""

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from threading import Lock
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr, ValidationError

from govbr_auth.core.errors import ExpiredTransactionError, InvalidStateError
from govbr_auth.core.models import AuthTransaction

_INVALID_STATE_MESSAGE = "OAuth state is invalid"
_EXPIRED_TRANSACTION_MESSAGE = "OAuth transaction has expired"
_INVALID_SECRET_MESSAGE = (
    "transaction secret must be a URL-safe base64-encoded 32-byte Fernet key; "
    "generate one with govbr_auth.generate_transaction_secret()"
)


def generate_transaction_secret() -> str:
    """Generate a URL-safe Fernet key for protecting OAuth transactions."""
    return Fernet.generate_key().decode("ascii")


class TransactionStore(Protocol):
    """Define storage operations for single-use OAuth transactions."""

    def create(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        """Create and protect a new OAuth transaction."""
        ...

    def consume(self, state: str, *, now: datetime) -> AuthTransaction:
        """Validate and atomically consume an OAuth transaction."""
        ...


class InMemoryTransactionStore:
    """Keep hashes of active transaction identifiers within one process."""

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
        self._active_transaction_hashes: dict[bytes, datetime] = {}
        self._lock = Lock()

    def create(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        """Create a protected transaction and retain only its identifier hash."""
        transaction = AuthTransaction(
            transaction_id=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            nonce=secrets.token_urlsafe(32),
            issued_at=now,
            expires_at=now + self._ttl,
        )
        payload = json.dumps(
            {
                "transaction_id": transaction.transaction_id,
                "code_verifier": transaction.code_verifier.get_secret_value(),
                "nonce": transaction.nonce.get_secret_value(),
                "issued_at": transaction.issued_at.isoformat(),
                "expires_at": transaction.expires_at.isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        state = self._fernet.encrypt(payload).decode("ascii")
        transaction_hash = self._hash_identifier(transaction.transaction_id)

        with self._lock:
            self._purge_expired_locked(now)
            self._active_transaction_hashes[transaction_hash] = transaction.expires_at

        return state, transaction

    def consume(self, state: str, *, now: datetime) -> AuthTransaction:
        """Authenticate, remove, and return a transaction exactly once."""
        self._require_timezone_aware(now)
        transaction = self._decode_transaction(state)

        transaction_hash = self._hash_identifier(transaction.transaction_id)
        with self._lock:
            registered_expires_at = self._active_transaction_hashes.pop(
                transaction_hash,
                None,
            )
            self._purge_expired_locked(now)

        if registered_expires_at is None:
            raise InvalidStateError(_INVALID_STATE_MESSAGE)
        if now >= registered_expires_at:
            raise ExpiredTransactionError(_EXPIRED_TRANSACTION_MESSAGE)

        return transaction

    @staticmethod
    def _hash_identifier(transaction_id: str) -> bytes:
        return hashlib.sha256(transaction_id.encode("utf-8")).digest()

    @staticmethod
    def _create_fernet(secret_value: str) -> Fernet:
        try:
            return Fernet(secret_value.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as error:
            failure_type = type(error).__name__

        safe_cause = ValueError(f"Fernet key validation failed ({failure_type})")
        raise ValueError(_INVALID_SECRET_MESSAGE) from safe_cause

    def _decode_transaction(self, state: str) -> AuthTransaction:
        try:
            payload = self._fernet.decrypt(state.encode("ascii"))
            return AuthTransaction.model_validate_json(payload)
        except (InvalidToken, UnicodeEncodeError, ValidationError) as error:
            failure_type = type(error).__name__

        safe_cause = ValueError(f"OAuth state validation failed ({failure_type})")
        raise InvalidStateError(_INVALID_STATE_MESSAGE) from safe_cause

    def _purge_expired_locked(self, now: datetime) -> None:
        self._active_transaction_hashes = {
            transaction_hash: expires_at
            for transaction_hash, expires_at in self._active_transaction_hashes.items()
            if now < expires_at
        }

    @staticmethod
    def _require_timezone_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
