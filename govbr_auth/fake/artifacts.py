"""Portable, encrypted artifacts used only by the Fake Gov.br provider."""

import json
from datetime import datetime
from typing import Literal, TypeVar

from cryptography.fernet import Fernet, InvalidToken
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

_INVALID_ARTIFACT_MESSAGE = "fake artifact is invalid"
_INVALID_SECRET_MESSAGE = "fake artifact secret is invalid"
_EXPIRED_ARTIFACT_MESSAGE = "fake artifact has expired"
_NOT_YET_VALID_ARTIFACT_MESSAGE = "fake artifact is not yet valid"


class _Artifact(BaseModel):
    """Provide shared immutable validation for encrypted fake artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    jti: str
    issued_at: datetime
    expires_at: datetime

    @field_validator("jti")
    @classmethod
    def validate_jti(cls, value: str) -> str:
        """Reject blank artifact identifiers."""
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("issued_at", "expires_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        """Reject timestamps without a UTC offset."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timestamp_ordering(self) -> "_Artifact":
        """Require every artifact to expire after it is issued."""
        if self.expires_at <= self.issued_at:
            raise ValueError("must be later than issued_at")
        return self


class AuthorizationRequestArtifact(_Artifact):
    """Describe a browser authorization request within the fake provider."""

    kind: Literal["authorization_request"] = "authorization_request"
    client_id: str
    redirect_uri: AnyHttpUrl
    state: str
    nonce: str
    scope: str
    code_challenge: str
    code_challenge_method: Literal["S256"] = "S256"


class AuthorizationCodeArtifact(_Artifact):
    """Describe an authorization code issued by the fake provider."""

    kind: Literal["authorization_code"] = "authorization_code"
    client_id: str
    redirect_uri: AnyHttpUrl
    nonce: str
    scope: str
    code_challenge: str
    code_challenge_method: Literal["S256"] = "S256"
    subject: str


class AccessTokenArtifact(_Artifact):
    """Describe an access token issued by the fake provider."""

    kind: Literal["access_token"] = "access_token"
    client_id: str
    subject: str
    scope: str
    issuer: str


ArtifactType = TypeVar("ArtifactType", bound=_Artifact)


class FakeArtifactCodec:
    """Encode and decode portable encrypted artifacts for Fake Gov.br only."""

    def __init__(self, secret: SecretStr) -> None:
        """Create a codec bound to one configured Fernet secret."""
        if not isinstance(secret, SecretStr):
            raise ValueError(_INVALID_SECRET_MESSAGE) from _safe_type_cause(
                "Fernet key validation"
            )
        self._fernet = self._create_fernet(secret.get_secret_value())

    def encode_authorization_request(
        self, artifact: AuthorizationRequestArtifact
    ) -> SecretStr:
        """Encrypt an authorization request artifact."""
        return self._encode(artifact, AuthorizationRequestArtifact)

    def decode_authorization_request(
        self, value: SecretStr, *, now: datetime
    ) -> AuthorizationRequestArtifact:
        """Decrypt and validate an authorization request artifact."""
        return self._decode(value, AuthorizationRequestArtifact, now=now)

    def encode_authorization_code(
        self, artifact: AuthorizationCodeArtifact
    ) -> SecretStr:
        """Encrypt an authorization code artifact."""
        return self._encode(artifact, AuthorizationCodeArtifact)

    def decode_authorization_code(
        self, value: SecretStr, *, now: datetime
    ) -> AuthorizationCodeArtifact:
        """Decrypt and validate an authorization code artifact."""
        return self._decode(value, AuthorizationCodeArtifact, now=now)

    def encode_access_token(self, artifact: AccessTokenArtifact) -> SecretStr:
        """Encrypt an access token artifact."""
        return self._encode(artifact, AccessTokenArtifact)

    def decode_access_token(
        self, value: SecretStr, *, now: datetime
    ) -> AccessTokenArtifact:
        """Decrypt and validate an access token artifact."""
        return self._decode(value, AccessTokenArtifact, now=now)

    @staticmethod
    def _create_fernet(secret_value: str) -> Fernet:
        try:
            return Fernet(secret_value.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as error:
            raise ValueError(_INVALID_SECRET_MESSAGE) from _safe_cause(
                "Fernet key validation", error
            )

    def _encode(
        self, artifact: _Artifact, artifact_type: type[ArtifactType]
    ) -> SecretStr:
        if not isinstance(artifact, artifact_type):
            raise ValueError(_INVALID_ARTIFACT_MESSAGE)
        payload = json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return SecretStr(self._fernet.encrypt(payload).decode("ascii"))

    def _decode(
        self, value: SecretStr, artifact_type: type[ArtifactType], *, now: datetime
    ) -> ArtifactType:
        _require_timezone_aware(now)
        if not isinstance(value, SecretStr):
            raise ValueError(_INVALID_ARTIFACT_MESSAGE) from _safe_type_cause(
                "fake artifact validation"
            )
        try:
            payload = self._fernet.decrypt(value.get_secret_value().encode("ascii"))
            artifact = artifact_type.model_validate(json.loads(payload.decode("utf-8")))
        except (
            InvalidToken,
            UnicodeDecodeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise ValueError(_INVALID_ARTIFACT_MESSAGE) from _safe_cause(
                "fake artifact validation", error
            )

        if now >= artifact.expires_at:
            raise ValueError(_EXPIRED_ARTIFACT_MESSAGE)
        if now < artifact.issued_at:
            raise ValueError(_NOT_YET_VALID_ARTIFACT_MESSAGE)
        return artifact


def _require_timezone_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")


def _safe_cause(context: str, error: Exception) -> ValueError:
    return ValueError(f"{context} failed ({type(error).__name__})")


def _safe_type_cause(context: str) -> ValueError:
    return ValueError(f"{context} failed (TypeError)")
