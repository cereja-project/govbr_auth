"""Strict configuration for the local Fake Gov.br provider."""

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)

from govbr_auth.fake.models import FakeClient

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class FakeGovBrSettings(BaseModel):
    """Validate immutable configuration without activating Fake Gov.br routes."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    base_url: AnyHttpUrl
    issuer: AnyHttpUrl
    artifact_secret: SecretStr
    request_ttl_seconds: PositiveInt
    authorization_code_ttl_seconds: PositiveInt
    access_token_ttl_seconds: PositiveInt
    id_token_ttl_seconds: PositiveInt
    clients: tuple[FakeClient, ...]
    post_logout_redirect_uris: tuple[AnyHttpUrl, ...] = ()
    allow_non_loopback: bool = False

    @field_validator("artifact_secret")
    @classmethod
    def validate_artifact_secret(cls, value: SecretStr) -> SecretStr:
        """Reject blank artifact secrets without disclosing their content."""
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("clients")
    @classmethod
    def validate_unique_client_ids(
        cls, value: tuple[FakeClient, ...]
    ) -> tuple[FakeClient, ...]:
        """Reject multiple registrations for the same client identifier."""
        if len({client.client_id for client in value}) != len(value):
            raise ValueError("duplicate fake client id")
        return value

    @model_validator(mode="after")
    def validate_loopback_hosts(self) -> "FakeGovBrSettings":
        """Restrict fake provider URLs to loopback hosts unless explicitly overridden."""
        if self.allow_non_loopback:
            return self
        for url in (self.base_url, self.issuer):
            host = (url.host or "").strip("[]").lower()
            if host not in _LOOPBACK_HOSTS:
                raise ValueError("fake provider must use a loopback host")
        return self
