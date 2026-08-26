"""Tests for protected, expirable, stateless OAuth transactions."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from govbr_auth.core.errors import ExpiredTransactionError, InvalidStateError
from govbr_auth.core.transactions import EncryptedTransactionCodec


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
def codec() -> EncryptedTransactionCodec:
    """Provide an isolated transaction codec with a fresh encryption key."""
    secret = SecretStr(Fernet.generate_key().decode("ascii"))
    return EncryptedTransactionCodec(secret=secret)


def _encrypted_envelope(
    key: bytes,
    *,
    issued_at: datetime,
    expires_at: datetime,
    version: int = 1,
    extra_transaction_fields: dict[str, str] | None = None,
) -> str:
    transaction = {
        "code_verifier": "v" * 64,
        "expires_at": expires_at.isoformat(),
        "issued_at": issued_at.isoformat(),
        "nonce": "n" * 43,
        "transaction_id": "transaction-123",
    }
    transaction.update(extra_transaction_fields or {})
    payload = {"transaction": transaction, "version": version}
    return Fernet(key).encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")


def test_codec_decodes_state_issued_by_another_instance_with_same_secret(
    clock: FrozenClock,
) -> None:
    secret = SecretStr(Fernet.generate_key().decode("ascii"))
    issuer = EncryptedTransactionCodec(secret)
    consumer = EncryptedTransactionCodec(secret)

    state, issued = issuer.issue(now=clock.now())

    assert consumer.decode(state, now=clock.now()) == issued


def test_codec_issues_a_versioned_transaction_envelope(clock: FrozenClock) -> None:
    key = Fernet.generate_key()
    codec = EncryptedTransactionCodec(SecretStr(key.decode("ascii")))

    state, issued = codec.issue(now=clock.now())

    payload = json.loads(Fernet(key).decrypt(state.encode("ascii")))
    assert payload == {
        "transaction": {
            "code_verifier": issued.code_verifier.get_secret_value(),
            "expires_at": issued.expires_at.isoformat(),
            "issued_at": issued.issued_at.isoformat(),
            "nonce": issued.nonce.get_secret_value(),
            "transaction_id": issued.transaction_id,
        },
        "version": 1,
    }


def test_decoded_transaction_preserves_nonce_verifier_and_lifetime(
    codec: EncryptedTransactionCodec,
    clock: FrozenClock,
) -> None:
    state, issued = codec.issue(now=clock.now())

    transaction = codec.decode(state, now=clock.now())

    assert transaction == issued
    assert len(transaction.code_verifier.get_secret_value()) in range(43, 129)
    assert len(transaction.nonce.get_secret_value()) >= 32
    assert transaction.issued_at == clock.now()
    assert transaction.expires_at == clock.now() + timedelta(minutes=5)


def test_issued_state_does_not_expose_transaction_secrets(
    codec: EncryptedTransactionCodec,
    clock: FrozenClock,
) -> None:
    state, transaction = codec.issue(now=clock.now())
    exposed_values = {
        transaction.transaction_id,
        transaction.code_verifier.get_secret_value(),
        transaction.nonce.get_secret_value(),
    }

    assert all(value not in state for value in exposed_values)


def test_same_state_can_be_decoded_by_independent_instances_during_ttl(
    clock: FrozenClock,
) -> None:
    secret = SecretStr(Fernet.generate_key().decode("ascii"))
    issuer = EncryptedTransactionCodec(secret)
    first_consumer = EncryptedTransactionCodec(secret)
    second_consumer = EncryptedTransactionCodec(secret)
    state, issued = issuer.issue(now=clock.now())

    first = first_consumer.decode(state, now=clock.now())
    second = second_consumer.decode(state, now=clock.now())

    assert (first, second) == (issued, issued)


def test_codec_rejects_tampered_state(
    codec: EncryptedTransactionCodec,
    clock: FrozenClock,
) -> None:
    state, _ = codec.issue(now=clock.now())
    middle = len(state) // 2
    replacement = "A" if state[middle] != "A" else "B"
    tampered_state = f"{state[:middle]}{replacement}{state[middle + 1:]}"

    with pytest.raises(InvalidStateError) as error:
        codec.decode(tampered_state, now=clock.now())

    assert str(error.value) == "OAuth state is invalid"


def test_invalid_payload_error_does_not_retain_sensitive_context(
    clock: FrozenClock,
) -> None:
    key = Fernet.generate_key()
    codec = EncryptedTransactionCodec(SecretStr(key.decode("ascii")))
    state = _encrypted_envelope(
        key,
        issued_at=clock.now(),
        expires_at=clock.now() + timedelta(minutes=5),
        extra_transaction_fields={"sensitive-state": "sensitive-value"},
    )

    with pytest.raises(InvalidStateError) as error:
        codec.decode(state, now=clock.now())

    assert str(error.value) == "OAuth state is invalid"
    assert error.value.__cause__ is not None
    assert "sensitive-state" not in str(error.value.__cause__)
    assert "sensitive-value" not in str(error.value.__cause__)
    assert "v" * 64 not in str(error.value.__cause__)
    assert "n" * 43 not in str(error.value.__cause__)
    assert error.value.__context__ is None


def test_codec_rejects_state_with_wrong_key(clock: FrozenClock) -> None:
    issuer = EncryptedTransactionCodec(
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    consumer = EncryptedTransactionCodec(
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    state, _ = issuer.issue(now=clock.now())

    with pytest.raises(InvalidStateError) as error:
        consumer.decode(state, now=clock.now())

    assert str(error.value) == "OAuth state is invalid"


def test_codec_rejects_unknown_envelope_version(clock: FrozenClock) -> None:
    key = Fernet.generate_key()
    codec = EncryptedTransactionCodec(SecretStr(key.decode("ascii")))
    state = _encrypted_envelope(
        key,
        issued_at=clock.now(),
        expires_at=clock.now() + timedelta(minutes=5),
        version=2,
    )

    with pytest.raises(InvalidStateError, match="OAuth state is invalid"):
        codec.decode(state, now=clock.now())


def test_codec_rejects_transaction_issued_in_the_future(clock: FrozenClock) -> None:
    key = Fernet.generate_key()
    codec = EncryptedTransactionCodec(SecretStr(key.decode("ascii")))
    state = _encrypted_envelope(
        key,
        issued_at=clock.now() + timedelta(seconds=1),
        expires_at=clock.now() + timedelta(minutes=5),
    )

    with pytest.raises(InvalidStateError, match="OAuth state is invalid"):
        codec.decode(state, now=clock.now())


def test_codec_rejects_expired_transaction(clock: FrozenClock) -> None:
    key = Fernet.generate_key()
    codec = EncryptedTransactionCodec(SecretStr(key.decode("ascii")))
    state = _encrypted_envelope(
        key,
        issued_at=clock.now() - timedelta(minutes=5),
        expires_at=clock.now(),
    )

    with pytest.raises(
        ExpiredTransactionError,
        match="OAuth transaction has expired",
    ):
        codec.decode(state, now=clock.now())


def test_outstanding_transactions_can_be_decoded_out_of_order(
    codec: EncryptedTransactionCodec,
    clock: FrozenClock,
) -> None:
    first_state, first_transaction = codec.issue(now=clock.now())
    second_state, second_transaction = codec.issue(now=clock.now())

    decoded_second = codec.decode(second_state, now=clock.now())
    decoded_first = codec.decode(first_state, now=clock.now())

    assert (decoded_second, decoded_first) == (
        second_transaction,
        first_transaction,
    )


def test_codec_issue_rejects_naive_current_time(
    codec: EncryptedTransactionCodec,
) -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        codec.issue(now=datetime(2026, 8, 11, 12, 0))


def test_codec_decode_rejects_naive_current_time(
    codec: EncryptedTransactionCodec,
    clock: FrozenClock,
) -> None:
    state, _ = codec.issue(now=clock.now())

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        codec.decode(state, now=datetime(2026, 8, 11, 12, 0))


def test_codec_rejects_blank_encryption_secret() -> None:
    with pytest.raises(ValueError) as error:
        EncryptedTransactionCodec(secret=SecretStr("   "))

    assert str(error.value) == "secret must not be empty"


@pytest.mark.parametrize(
    "invalid_secret",
    ["invalid-sensitive-key-material", "segredo-sensível-não-ascii"],
)
def test_codec_sanitizes_invalid_encryption_secret(invalid_secret: str) -> None:
    with pytest.raises(ValueError) as error:
        EncryptedTransactionCodec(secret=SecretStr(invalid_secret))

    assert str(error.value) == (
        "transaction secret must be a URL-safe base64-encoded 32-byte Fernet "
        "key; generate one with govbr_auth.generate_transaction_secret()"
    )
    assert error.value.__cause__ is not None
    assert invalid_secret not in str(error.value.__cause__)
    assert error.value.__context__ is None


def test_codec_rejects_non_positive_ttl() -> None:
    secret = SecretStr(Fernet.generate_key().decode("ascii"))

    with pytest.raises(ValueError) as error:
        EncryptedTransactionCodec(secret=secret, ttl=timedelta(0))

    assert str(error.value) == "ttl must be positive"
