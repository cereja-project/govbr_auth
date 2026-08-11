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

        self._fernet = Fernet(secret_value.encode("ascii"))
        self._ttl = ttl
        self._active_transaction_hashes: set[bytes] = set()
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
            self._active_transaction_hashes.add(transaction_hash)

        return state, transaction

    def consume(self, state: str, *, now: datetime) -> AuthTransaction:
        """Authenticate, remove, and return a transaction exactly once."""
        self._require_timezone_aware(now)

        try:
            payload = self._fernet.decrypt(state.encode("ascii"))
            transaction = AuthTransaction.model_validate_json(payload)
        except (InvalidToken, UnicodeEncodeError, ValidationError):
            raise InvalidStateError(_INVALID_STATE_MESSAGE) from None

        transaction_hash = self._hash_identifier(transaction.transaction_id)
        with self._lock:
            if transaction_hash not in self._active_transaction_hashes:
                raise InvalidStateError(_INVALID_STATE_MESSAGE)
            self._active_transaction_hashes.remove(transaction_hash)

        if now >= transaction.expires_at:
            raise ExpiredTransactionError(_EXPIRED_TRANSACTION_MESSAGE)

        return transaction

    @staticmethod
    def _hash_identifier(transaction_id: str) -> bytes:
        return hashlib.sha256(transaction_id.encode("utf-8")).digest()

    @staticmethod
    def _require_timezone_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
