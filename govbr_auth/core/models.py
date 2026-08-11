"""Immutable domain models for the new Gov.br OAuth core."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, PositiveInt, SecretStr, field_validator, model_validator


class AuthTransaction(BaseModel):
    """Store the short-lived values created for one OAuth authorization flow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_id: str
    code_verifier: SecretStr
    nonce: SecretStr
    issued_at: datetime
    expires_at: datetime

    @field_validator("issued_at", "expires_at")
    @classmethod
    def validate_timezone_aware_datetime(cls, value: datetime) -> datetime:
        """Reject transaction timestamps that do not carry an explicit timezone."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transaction timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_expiration(self) -> "AuthTransaction":
        """Reject transactions whose expiration does not follow their issuance."""
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        return self


class TokenSet(BaseModel):
    """Store the OAuth tokens returned by a successful authorization flow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: SecretStr
    id_token: SecretStr
    token_type: Literal["Bearer"]
    expires_in: PositiveInt
    scope: str


class GovBrAddress(BaseModel):
    """Represent the standard address claim returned by OpenID Connect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    formatted: str | None = None
    street_address: str | None = None
    locality: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None


class GovBrUser(BaseModel):
    """Represent the standard OpenID Connect claims exposed for a Gov.br user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sub: str
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    nickname: str | None = None
    preferred_username: str | None = None
    profile: str | None = None
    picture: str | None = None
    website: str | None = None
    email: str | None = None
    email_verified: bool | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None
    phone_number_verified: bool | None = None
    address: GovBrAddress | None = None
    updated_at: int | None = None
