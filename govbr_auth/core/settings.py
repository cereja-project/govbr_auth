"""Strict configuration for the new Gov.br OAuth core."""

from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, NonNegativeInt, PositiveFloat, SecretStr, model_validator


class ProviderEnvironment(StrEnum):
    """Identify the Gov.br provider deployment used by the application."""

    PRODUCTION = "production"
    STAGING = "staging"
    LOCAL = "local"


class GovBrSettings(BaseModel):
    """Validate immutable configuration for a Gov.br OAuth provider."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    environment: ProviderEnvironment = ProviderEnvironment.PRODUCTION
    authorization_url: AnyHttpUrl
    token_url: AnyHttpUrl
    userinfo_url: AnyHttpUrl
    client_id: str
    client_secret: SecretStr
    redirect_uri: AnyHttpUrl
    scope: str = "openid profile email"
    transaction_secret: SecretStr
    issuer: AnyHttpUrl
    jwks_url: AnyHttpUrl
    connect_timeout_seconds: PositiveFloat = 5.0
    read_timeout_seconds: PositiveFloat = 10.0
    clock_skew_seconds: NonNegativeInt = 60

    @model_validator(mode="after")
    def validate_url_schemes(self) -> "GovBrSettings":
        """Require HTTPS except for explicit loopback-only local configuration."""
        for url in self._configured_urls():
            if url.scheme == "https":
                continue
            if self.environment is not ProviderEnvironment.LOCAL:
                raise ValueError("provider URLs must use https outside the local environment")
            if url.host not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("local HTTP provider URLs must use a loopback host")
        return self

    def _configured_urls(self) -> tuple[AnyHttpUrl, ...]:
        """Return every URL that participates in the configured OAuth exchange."""
        return (
            self.authorization_url,
            self.token_url,
            self.userinfo_url,
            self.redirect_uri,
            self.issuer,
            self.jwks_url,
        )
