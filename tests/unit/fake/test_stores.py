"""Tests for in-memory Fake Gov.br stores."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from govbr_auth.fake import (
    AuthorizationCodeReplayStore,
    FakeUser,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _consume_identifier(
    store: AuthorizationCodeReplayStore,
    identifier: str,
    expires_at: datetime,
    now: datetime,
) -> bool:
    return store.consume(identifier, expires_at=expires_at, now=now)


def test_user_store_returns_user_by_subject() -> None:
    expected_user = FakeUser(sub="subject-123", name="Maria da Silva")
    store = InMemoryFakeUserStore((expected_user,))

    user = store.get("subject-123")

    assert user == expected_user


def test_user_store_returns_immutable_snapshot() -> None:
    expected_user = FakeUser(sub="subject-123", name="Maria da Silva")
    store = InMemoryFakeUserStore((expected_user,))

    snapshot = store.list()

    assert snapshot == (expected_user,)

    with pytest.raises(ValidationError, match="frozen"):
        snapshot[0].name = "Another Name"


def test_user_store_rejects_duplicate_subjects() -> None:
    duplicate_users = (FakeUser(sub="subject-123"), FakeUser(sub="subject-123"))

    with pytest.raises(ValueError, match="duplicate fake user subject"):
        InMemoryFakeUserStore(duplicate_users)


def test_replay_store_consumes_identifier_once(now: datetime) -> None:
    store = InMemoryAuthorizationCodeReplayStore()

    first = store.consume("code-id", expires_at=now + timedelta(minutes=1), now=now)
    second = store.consume("code-id", expires_at=now + timedelta(minutes=1), now=now)

    assert first is True
    assert second is False


def test_replay_store_purges_an_expired_identifier(now: datetime) -> None:
    store = InMemoryAuthorizationCodeReplayStore()

    first = store.consume("code-id", expires_at=now + timedelta(seconds=1), now=now)
    second = store.consume(
        "code-id",
        expires_at=now + timedelta(minutes=1),
        now=now + timedelta(seconds=1),
    )

    assert first is True
    assert second is True


def test_replay_store_rejects_expired_identifier(now: datetime) -> None:
    store = InMemoryAuthorizationCodeReplayStore()

    accepted = store.consume("code-id", expires_at=now - timedelta(seconds=1), now=now)

    assert accepted is False


def test_replay_store_allows_one_concurrent_consume(now: datetime) -> None:
    store = InMemoryAuthorizationCodeReplayStore()
    expires_at = now + timedelta(minutes=1)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(
            executor.map(
                _consume_identifier,
                (store,) * 16,
                ("code-id",) * 16,
                (expires_at,) * 16,
                (now,) * 16,
            )
        )

    assert results.count(True) == 1
    assert results.count(False) == 15


@pytest.mark.parametrize(
    "identifier",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
    ],
)
def test_replay_store_rejects_blank_identifier(identifier: str, now: datetime) -> None:
    store = InMemoryAuthorizationCodeReplayStore()

    with pytest.raises(ValueError, match="must not be empty"):
        store.consume(identifier, expires_at=now + timedelta(minutes=1), now=now)


@pytest.mark.parametrize(
    "expires_at, current_time",
    [
        pytest.param(
            datetime(2026, 8, 12, 12, 1),
            datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
            id="naive_expiration",
        ),
        pytest.param(
            datetime(2026, 8, 12, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 12, 0),
            id="naive_current_time",
        ),
    ],
)
def test_replay_store_rejects_naive_times(
    expires_at: datetime, current_time: datetime
) -> None:
    store = InMemoryAuthorizationCodeReplayStore()

    with pytest.raises(ValueError, match="timezone-aware"):
        store.consume("code-id", expires_at=expires_at, now=current_time)
