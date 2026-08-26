"""In-memory storage primitives for the local Fake Gov.br provider."""

from datetime import datetime
from threading import Lock
from typing import Protocol

from govbr_auth.fake.models import FakeUser


class FakeUserStore(Protocol):
    """Describe read access to the configured fake users."""

    def get(self, subject: str) -> FakeUser | None: ...

    def list(self) -> tuple[FakeUser, ...]: ...


class AuthorizationCodeReplayStore(Protocol):
    """Describe atomic authorization-code replay prevention."""

    def consume(
        self,
        identifier: str,
        *,
        expires_at: datetime,
        now: datetime,
    ) -> bool: ...


class InMemoryFakeUserStore:
    """Store immutable fake-user snapshots in process memory."""

    def __init__(self, users: tuple[FakeUser, ...] = ()) -> None:
        """Build a store while rejecting duplicate stable subjects."""
        self._users_by_subject: dict[str, FakeUser] = {}
        for user in users:
            if user.sub in self._users_by_subject:
                raise ValueError("duplicate fake user subject")
            self._users_by_subject[user.sub] = user

    def get(self, subject: str) -> FakeUser | None:
        """Return the fake user registered for a stable subject, if any."""
        return self._users_by_subject.get(subject)

    def list(self) -> tuple[FakeUser, ...]:
        """Return an immutable snapshot of every registered fake user."""
        return tuple(self._users_by_subject.values())


class InMemoryAuthorizationCodeReplayStore:
    """Atomically track consumed authorization-code identifiers in memory."""

    def __init__(self) -> None:
        """Create an empty replay store guarded by a per-instance lock."""
        self._consumed_identifiers: dict[str, datetime] = {}
        self._lock = Lock()

    def consume(
        self,
        identifier: str,
        *,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Consume a valid identifier once, rejecting expiry and replay attempts."""
        self._validate_identifier(identifier)
        self._validate_aware_times(expires_at=expires_at, now=now)

        with self._lock:
            self._purge_expired(now)
            if expires_at <= now:
                return False
            if identifier in self._consumed_identifiers:
                return False
            self._consumed_identifiers[identifier] = expires_at
            return True

    @staticmethod
    def _validate_identifier(identifier: str) -> None:
        if not identifier.strip():
            raise ValueError("must not be empty")

    @staticmethod
    def _validate_aware_times(*, expires_at: datetime, now: datetime) -> None:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

    def _purge_expired(self, now: datetime) -> None:
        expired_identifiers = tuple(
            identifier
            for identifier, expires_at in self._consumed_identifiers.items()
            if expires_at <= now
        )
        for identifier in expired_identifiers:
            del self._consumed_identifiers[identifier]
