"""Tests for portable encrypted Fake Gov.br artifacts."""

import json
from datetime import datetime, timedelta, timezone, tzinfo

from cryptography.fernet import Fernet
import pytest
from pydantic import SecretStr, ValidationError

from govbr_auth.fake import (
    AccessTokenArtifact,
    AuthorizationCodeArtifact,
    AuthorizationRequestArtifact,
    FakeArtifactCodec,
)


class _TimezoneWithoutOffset(tzinfo):
    def dst(self, value: datetime | None) -> timedelta | None:
        return None

    def tzname(self, value: datetime | None) -> str | None:
        return None

    def utcoffset(self, value: datetime | None) -> timedelta | None:
        return None


def _encrypt_payload(key: str, payload: object) -> SecretStr:
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return SecretStr(Fernet(key.encode("ascii")).encrypt(serialized).decode("ascii"))


def _assert_sanitized(error: ValueError, marker: str) -> None:
    pending = [error]
    visited: set[int] = set()

    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))

        details = f"{current!s} {current!r} {current.args!r} {current.__dict__!r}"

        assert marker not in details

        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


def test_authorization_request_round_trips_between_independent_codecs() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AuthorizationRequestArtifact(
        jti="request-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        client_id="client-123",
        redirect_uri="https://client.example/callback",
        state="state-123",
        nonce="nonce-123",
        scope="openid profile",
        code_challenge="challenge-123",
    )

    encoded = FakeArtifactCodec(SecretStr(key)).encode_authorization_request(artifact)
    decoded = FakeArtifactCodec(SecretStr(key)).decode_authorization_request(
        encoded, now=now
    )

    assert decoded == artifact


def test_authorization_code_round_trips_between_independent_codecs() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AuthorizationCodeArtifact(
        jti="code-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=1),
        client_id="client-123",
        redirect_uri="https://client.example/callback",
        nonce="nonce-123",
        scope="openid profile",
        code_challenge="challenge-123",
        subject="subject-123",
    )

    encoded = FakeArtifactCodec(SecretStr(key)).encode_authorization_code(artifact)
    decoded = FakeArtifactCodec(SecretStr(key)).decode_authorization_code(
        encoded, now=now
    )

    assert decoded == artifact


def test_access_token_round_trips_between_independent_codecs() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )

    encoded = FakeArtifactCodec(SecretStr(key)).encode_access_token(artifact)
    decoded = FakeArtifactCodec(SecretStr(key)).decode_access_token(encoded, now=now)

    assert decoded == artifact


def test_authorization_request_encoder_rejects_another_artifact_type() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    authorization_code = AuthorizationCodeArtifact(
        jti="code-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=1),
        client_id="client-123",
        redirect_uri="https://client.example/callback",
        nonce="nonce-123",
        scope="openid profile",
        code_challenge="challenge-123",
        subject="subject-123",
    )
    codec = FakeArtifactCodec(SecretStr(Fernet.generate_key().decode("ascii")))

    with pytest.raises(ValueError, match="fake artifact is invalid"):
        codec.encode_authorization_request(authorization_code)


def test_artifact_models_reject_blank_identifier() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="must not be empty"):
        AuthorizationRequestArtifact(
            jti="   ",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            client_id="client-123",
            redirect_uri="https://client.example/callback",
            state="state-123",
            nonce="nonce-123",
            scope="openid profile",
            code_challenge="challenge-123",
        )


def test_artifact_models_reject_naive_timestamps() -> None:
    issued_at = datetime(2026, 8, 12, 12, 0)

    with pytest.raises(ValidationError, match="timezone-aware"):
        AccessTokenArtifact(
            jti="token-123",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=10),
            client_id="client-123",
            subject="subject-123",
            scope="openid profile",
            issuer="https://fake.gov.br",
        )


def test_artifact_models_reject_timestamps_without_offset() -> None:
    issued_at = datetime(2026, 8, 12, 12, 0, tzinfo=_TimezoneWithoutOffset())

    with pytest.raises(ValidationError, match="timezone-aware"):
        AccessTokenArtifact(
            jti="token-123",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=10),
            client_id="client-123",
            subject="subject-123",
            scope="openid profile",
            issuer="https://fake.gov.br",
        )


def test_artifact_models_reject_non_increasing_timestamps() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="later than issued_at"):
        AccessTokenArtifact(
            jti="token-123",
            issued_at=now,
            expires_at=now,
            client_id="client-123",
            subject="subject-123",
            scope="openid profile",
            issuer="https://fake.gov.br",
        )


def test_artifact_models_reject_incorrect_kind() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="authorization_request"):
        AuthorizationRequestArtifact(
            kind="access_token",
            jti="request-123",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            client_id="client-123",
            redirect_uri="https://client.example/callback",
            state="state-123",
            nonce="nonce-123",
            scope="openid profile",
            code_challenge="challenge-123",
        )


def test_artifact_models_hide_invalid_input_from_validation_error() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    marker = "sensitive-code-challenge-method"

    with pytest.raises(ValidationError) as error:
        AuthorizationRequestArtifact(
            jti="request-123",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            client_id="client-123",
            redirect_uri="https://client.example/callback",
            state="state-123",
            nonce="nonce-123",
            scope="openid profile",
            code_challenge="challenge-123",
            code_challenge_method=marker,
        )

    _assert_sanitized(error.value, marker)


def test_codec_rejects_invalid_fernet_secret_without_leaking_it() -> None:
    marker = "sensitive-key-marker-🔐"

    with pytest.raises(ValueError, match="fake artifact secret is invalid") as error:
        FakeArtifactCodec(SecretStr(marker))

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, marker)


def test_codec_rejects_non_secret_string_key_without_leaking_it() -> None:
    marker = "sensitive-key-marker"

    with pytest.raises(ValueError, match="fake artifact secret is invalid") as error:
        FakeArtifactCodec(marker)  # type: ignore[arg-type]

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, marker)


def test_decoder_rejects_non_secret_string_artifact_without_leaking_it() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    codec = FakeArtifactCodec(SecretStr(Fernet.generate_key().decode("ascii")))
    marker = "sensitive-artifact-marker"

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(marker, now=now)  # type: ignore[arg-type]

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, marker)


def test_decoder_rejects_an_artifact_from_another_key_without_leaking_input() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    encoded = FakeArtifactCodec(
        SecretStr(Fernet.generate_key().decode("ascii"))
    ).encode_access_token(artifact)
    codec = FakeArtifactCodec(SecretStr(Fernet.generate_key().decode("ascii")))

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(encoded, now=now)

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, encoded.get_secret_value())


def test_decoder_rejects_tampered_artifact_without_leaking_input() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    codec = FakeArtifactCodec(SecretStr(Fernet.generate_key().decode("ascii")))
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    encoded = codec.encode_access_token(artifact).get_secret_value()
    replacement = "A" if encoded[-1] != "A" else "B"
    tampered = SecretStr(f"{encoded[:-1]}{replacement}")

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(tampered, now=now)

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, tampered.get_secret_value())


def test_decoder_rejects_non_ascii_artifact_text_without_leaking_input() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    codec = FakeArtifactCodec(SecretStr(Fernet.generate_key().decode("ascii")))
    marker = "sensitive-artifact-marker-🔐"

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(SecretStr(marker), now=now)

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, marker)


def test_decoder_rejects_malformed_json_without_leaking_artifact_data() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    codec = FakeArtifactCodec(SecretStr(key))
    marker = "sensitive-artifact-data"
    malformed = SecretStr(
        Fernet(key.encode("ascii")).encrypt(marker.encode("utf-8")).decode("ascii")
    )

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(malformed, now=now)

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, marker)


def test_decoder_rejects_missing_artifact_field_without_leaking_data() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="sensitive-subject-marker",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    payload = artifact.model_dump(mode="json")
    del payload["subject"]
    codec = FakeArtifactCodec(SecretStr(key))

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(_encrypt_payload(key, payload), now=now)

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, "sensitive-subject-marker")


def test_decoder_rejects_extra_artifact_field_without_leaking_data() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    payload = artifact.model_dump(mode="json")
    payload["unexpected"] = "sensitive-extra-marker"
    codec = FakeArtifactCodec(SecretStr(key))

    with pytest.raises(ValueError, match="fake artifact is invalid") as error:
        codec.decode_access_token(_encrypt_payload(key, payload), now=now)

    assert error.value.__cause__ is not None
    _assert_sanitized(error.value, "sensitive-extra-marker")


def test_decoder_rejects_an_artifact_with_another_kind() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    codec = FakeArtifactCodec(SecretStr(key))
    encoded = codec.encode_access_token(artifact)

    with pytest.raises(ValueError, match="fake artifact is invalid"):
        codec.decode_authorization_request(encoded, now=now)


def test_decoder_rejects_expired_artifact() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now - timedelta(minutes=10),
        expires_at=now,
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    codec = FakeArtifactCodec(SecretStr(key))

    with pytest.raises(ValueError, match="fake artifact has expired"):
        codec.decode_access_token(codec.encode_access_token(artifact), now=now)


def test_decoder_rejects_artifact_issued_in_the_future() -> None:
    key = Fernet.generate_key().decode("ascii")
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=now + timedelta(seconds=1),
        expires_at=now + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    codec = FakeArtifactCodec(SecretStr(key))

    with pytest.raises(ValueError, match="fake artifact is not yet valid"):
        codec.decode_access_token(codec.encode_access_token(artifact), now=now)


def test_decoder_rejects_naive_current_time() -> None:
    key = Fernet.generate_key().decode("ascii")
    issued_at = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    codec = FakeArtifactCodec(SecretStr(key))

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        codec.decode_access_token(
            codec.encode_access_token(artifact), now=datetime(2026, 8, 12, 12, 0)
        )


def test_decoder_rejects_current_time_without_offset() -> None:
    key = Fernet.generate_key().decode("ascii")
    issued_at = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    artifact = AccessTokenArtifact(
        jti="token-123",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=10),
        client_id="client-123",
        subject="subject-123",
        scope="openid profile",
        issuer="https://fake.gov.br",
    )
    codec = FakeArtifactCodec(SecretStr(key))
    now = datetime(2026, 8, 12, 12, 0, tzinfo=_TimezoneWithoutOffset())

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        codec.decode_access_token(codec.encode_access_token(artifact), now=now)
