"""Strict configuration for the new Gov.br OAuth core."""

from enum import StrEnum

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    NonNegativeInt,
    PositiveFloat,
    SecretStr,
    field_validator,
    model_validator,
)


class ProviderEnvironment(StrEnum):
    """Identify the Gov.br provider deployment used by the application."""

    PRODUCTION = "production"
    STAGING = "staging"
    LOCAL = "local"


class GovBrSettings(BaseModel):
    """Validate immutable configuration for a Gov.br OAuth provider."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

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

    @field_validator("client_id", "scope")
    @classmethod
    def validate_nonempty_text(cls, value: str) -> str:
        """Reject empty values needed to create a valid OAuth request."""
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("client_secret", "transaction_secret")
    @classmethod
    def validate_nonempty_secret(cls, value: SecretStr) -> SecretStr:
        """Reject whitespace-only credentials without exposing their contents."""
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_url_schemes(self) -> "GovBrSettings":
        """Require HTTPS except for loopback-only configuration."""
        for environment_name, url in self._configured_urls():
            if url.scheme == "https":
                continue
            host = (url.host or "").strip("[]")
            if host not in {"localhost", "127.0.0.1", "::1"}:
                if environment_name == "GOVBR_REDIRECT_URI":
                    correction = (
                        "Configure HTTPS para esse DNS ou use uma URI de loopback"
                    )
                else:
                    correction = "Configure HTTPS ou use um endpoint de loopback"
                raise ValueError(
                    f"{environment_name} usa HTTP em um host não-loopback. "
                    f"{correction}"
                )
        return self

    @model_validator(mode="after")
    def validate_official_provider_environment(self) -> "GovBrSettings":
        """Reject official Gov.br endpoints from another deployment."""
        mismatched_variables = [
            environment_name
            for environment_name, url in self._provider_urls()
            if _OFFICIAL_GOVBR_HOST_ENVIRONMENTS.get(url.host.rstrip(".")) is not None
            and _OFFICIAL_GOVBR_HOST_ENVIRONMENTS[url.host.rstrip(".")]
            is not self.environment
        ]
        if mismatched_variables:
            rendered_variables = ", ".join(mismatched_variables)
            raise ValueError(
                "Endpoints oficiais do Gov.br incompatíveis com "
                f"GOVBR_ENVIRONMENT='{self.environment.value}': "
                f"{rendered_variables}"
            )
        return self

    def _configured_urls(self) -> tuple[tuple[str, AnyHttpUrl], ...]:
        """Return every OAuth URL with its public environment name."""
        return (
            ("GOVBR_AUTHORIZATION_URL", self.authorization_url),
            ("GOVBR_TOKEN_URL", self.token_url),
            ("GOVBR_USERINFO_URL", self.userinfo_url),
            ("GOVBR_REDIRECT_URI", self.redirect_uri),
            ("GOVBR_ISSUER", self.issuer),
            ("GOVBR_JWKS_URL", self.jwks_url),
        )

    def _provider_urls(self) -> tuple[tuple[str, AnyHttpUrl], ...]:
        """Return provider endpoints with their public environment names."""
        return (
            ("GOVBR_AUTHORIZATION_URL", self.authorization_url),
            ("GOVBR_TOKEN_URL", self.token_url),
            ("GOVBR_USERINFO_URL", self.userinfo_url),
            ("GOVBR_ISSUER", self.issuer),
            ("GOVBR_JWKS_URL", self.jwks_url),
        )


_OFFICIAL_GOVBR_HOST_ENVIRONMENTS = {
    "sso.acesso.gov.br": ProviderEnvironment.PRODUCTION,
    "sso.staging.acesso.gov.br": ProviderEnvironment.STAGING,
}
