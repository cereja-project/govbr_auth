"""Tests for protected, expirable, single-use OAuth transactions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from govbr_auth.core.errors import ExpiredTransactionError, InvalidStateError
from govbr_auth.core.models import AuthTransaction
from govbr_auth.core.transactions import InMemoryTransactionStore


@dataclass(frozen=True, slots=True)
class FrozenClock:
    """Return a fixed timezone-aware instant for transaction tests."""

    current: datetime

    def now(self) -> datetime:
        """Return the configured instant."""
        return self.current


@pytest.fixture
def clock() -> FrozenClock:
    """Provide a deterministic UTC clock."""
    return FrozenClock(datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc))


@pytest.fixture
def store() -> InMemoryTransactionStore:
    """Provide an isolated transaction store with a fresh encryption key."""
    secret = SecretStr(Fernet.generate_key().decode("ascii"))
    return InMemoryTransactionStore(secret=secret)


def test_consuming_transaction_returns_original_nonce_and_verifier(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, created = store.create(now=clock.now())

    transaction = store.consume(state, now=clock.now())

    assert transaction == created
    assert len(transaction.code_verifier.get_secret_value()) in range(43, 129)
    assert len(transaction.nonce.get_secret_value()) >= 32
    assert transaction.issued_at == clock.now()
    assert transaction.expires_at == clock.now() + timedelta(minutes=5)


def test_created_state_does_not_expose_transaction_secrets(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, transaction = store.create(now=clock.now())

    exposed_values = {
        transaction.transaction_id,
        transaction.code_verifier.get_secret_value(),
        transaction.nonce.get_secret_value(),
    }

    assert all(value not in state for value in exposed_values)


def test_consuming_same_state_twice_rejects_replay(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, _ = store.create(now=clock.now())
    store.consume(state, now=clock.now())

    with pytest.raises(InvalidStateError, match="OAuth state is invalid"):
        store.consume(state, now=clock.now())


def test_concurrent_consumption_allows_exactly_one_use(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, transaction = store.create(now=clock.now())
    barrier = Barrier(2)

    def consume_after_barrier() -> AuthTransaction:
        barrier.wait()
        return store.consume(state, now=clock.now())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(consume_after_barrier) for _ in range(2)]

    results = [future.result() for future in futures if future.exception() is None]
    errors = [
        future.exception() for future in futures if future.exception() is not None
    ]

    assert results == [transaction]
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidStateError)


def test_consuming_tampered_state_rejects_transaction(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, _ = store.create(now=clock.now())
    middle = len(state) // 2
    replacement = "A" if state[middle] != "A" else "B"
    tampered_state = f"{state[:middle]}{replacement}{state[middle + 1:]}"

    with pytest.raises(InvalidStateError, match="OAuth state is invalid"):
        store.consume(tampered_state, now=clock.now())


def test_consuming_state_with_wrong_key_rejects_transaction(clock: FrozenClock) -> None:
    issuing_store = InMemoryTransactionStore(
        secret=SecretStr(Fernet.generate_key().decode("ascii")),
    )
    consuming_store = InMemoryTransactionStore(
        secret=SecretStr(Fernet.generate_key().decode("ascii")),
    )
    state, _ = issuing_store.create(now=clock.now())

    with pytest.raises(InvalidStateError, match="OAuth state is invalid"):
        consuming_store.consume(state, now=clock.now())


def test_consuming_expired_state_rejects_transaction(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, transaction = store.create(now=clock.now())

    with pytest.raises(ExpiredTransactionError, match="OAuth transaction has expired"):
        store.consume(state, now=transaction.expires_at)


def test_outstanding_transactions_can_be_consumed_out_of_order(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    first_state, first_transaction = store.create(now=clock.now())
    second_state, second_transaction = store.create(now=clock.now())

    consumed_second = store.consume(second_state, now=clock.now())
    consumed_first = store.consume(first_state, now=clock.now())

    assert (consumed_second, consumed_first) == (second_transaction, first_transaction)


def test_create_rejects_naive_current_time(store: InMemoryTransactionStore) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        store.create(now=datetime(2026, 8, 11, 12, 0))


def test_consume_rejects_naive_current_time(
    store: InMemoryTransactionStore,
    clock: FrozenClock,
) -> None:
    state, _ = store.create(now=clock.now())

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        store.consume(state, now=datetime(2026, 8, 11, 12, 0))


def test_store_rejects_blank_encryption_secret() -> None:
    with pytest.raises(ValueError, match="secret must not be empty"):
        InMemoryTransactionStore(secret=SecretStr("   "))


def test_store_rejects_non_positive_ttl() -> None:
    secret = SecretStr(Fernet.generate_key().decode("ascii"))

    with pytest.raises(ValueError, match="ttl must be positive"):
        InMemoryTransactionStore(secret=secret, ttl=timedelta(0))
