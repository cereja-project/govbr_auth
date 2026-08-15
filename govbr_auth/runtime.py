"""Framework-neutral configuration for selecting a Gov.br runtime provider."""

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    PositiveInt,
    SecretStr,
    field_validator,
)

from govbr_auth.core.settings import GovBrSettings


class GovBrProvider(StrEnum):
    """Select the provider used by a runtime composition root."""

    OFFICIAL = "official"
    FAKE = "fake"


class GovBrRuntimeSettings(BaseModel):
    """Keep provider selection and runtime inputs independent of web frameworks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: GovBrProvider = GovBrProvider.OFFICIAL
    oauth: GovBrSettings | None = None
    fake_end_to_end: bool = False
    fake_host: str = "127.0.0.1"
    fake_port: int = 8000
    fake_provider_prefix: str = "/fake-govbr"
    fake_client_id: str = "govbr-auth-local"
    fake_client_secret: SecretStr = SecretStr("local-fake-only")
    fake_redirect_uri: AnyHttpUrl | None = None
    fake_request_ttl_seconds: PositiveInt = 300
    fake_authorization_code_ttl_seconds: PositiveInt = 60
    fake_access_token_ttl_seconds: PositiveInt = 600
    fake_id_token_ttl_seconds: PositiveInt = 300
    fake_users_file: Path | None = None

    @field_validator("fake_end_to_end", mode="before")
    @classmethod
    def validate_fake_end_to_end(cls, value: object) -> bool:
        """Accept only canonical environment boolean spellings."""
        if isinstance(value, bool):
            return value
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("must be 'true' or 'false'")

    @field_validator("fake_host")
    @classmethod
    def validate_fake_host(cls, value: str) -> str:
        """Restrict the local fake runtime to loopback interfaces."""
        if value not in _LOOPBACK_HOSTS:
            raise ValueError("fake host must be a loopback host")
        return value

    @field_validator("fake_port")
    @classmethod
    def validate_fake_port(cls, value: int) -> int:
        """Restrict the fake runtime to the valid TCP port range."""
        if not 1 <= value <= 65535:
            raise ValueError("fake port must be between 1 and 65535")
        return value

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "GovBrRuntimeSettings":
        """Build validated settings from an explicit environment mapping."""
        values = os.environ if environ is None else environ
        return cls.model_validate(_runtime_values(values))


def _runtime_values(environ: Mapping[str, str]) -> dict[str, object]:
    """Select only the environment inputs relevant to the chosen provider."""
    provider = environ.get("GOVBR_PROVIDER", GovBrProvider.OFFICIAL.value)
    values: dict[str, object] = {"provider": provider}

    if provider == GovBrProvider.OFFICIAL.value:
        oauth_values = _prefixed_values(environ, _OFFICIAL_OAUTH_FIELDS)
        if oauth_values:
            values["oauth"] = oauth_values
    elif provider == GovBrProvider.FAKE.value:
        values.update(_prefixed_values(environ, _FAKE_FIELDS))
        if (
            values.get("fake_end_to_end") == "true"
            and "fake_redirect_uri" not in values
        ):
            values["fake_redirect_uri"] = _default_fake_redirect_uri(values)

    return values


def _prefixed_values(
    environ: Mapping[str, str], fields: Mapping[str, str]
) -> dict[str, str]:
    """Map present GOVBR_ variables to their model field names."""
    return {
        field_name: environ[environment_name]
        for environment_name, field_name in fields.items()
        if environment_name in environ
    }


def _default_fake_redirect_uri(values: Mapping[str, object]) -> str:
    """Return the callback URL used by the local end-to-end runtime."""
    host = str(values.get("fake_host", "127.0.0.1"))
    rendered_host = f"[{host}]" if host == "::1" else host
    port = values.get("fake_port", 8000)
    return f"http://{rendered_host}:{port}/auth/govbr/callback"


_OFFICIAL_OAUTH_FIELDS = {
    "GOVBR_ENVIRONMENT": "environment",
    "GOVBR_AUTHORIZATION_URL": "authorization_url",
    "GOVBR_TOKEN_URL": "token_url",
    "GOVBR_USERINFO_URL": "userinfo_url",
    "GOVBR_CLIENT_ID": "client_id",
    "GOVBR_CLIENT_SECRET": "client_secret",
    "GOVBR_REDIRECT_URI": "redirect_uri",
    "GOVBR_SCOPE": "scope",
    "GOVBR_TRANSACTION_SECRET": "transaction_secret",
    "GOVBR_ISSUER": "issuer",
    "GOVBR_JWKS_URL": "jwks_url",
    "GOVBR_CONNECT_TIMEOUT_SECONDS": "connect_timeout_seconds",
    "GOVBR_READ_TIMEOUT_SECONDS": "read_timeout_seconds",
    "GOVBR_CLOCK_SKEW_SECONDS": "clock_skew_seconds",
}

_FAKE_FIELDS = {
    "GOVBR_FAKE_END_TO_END": "fake_end_to_end",
    "GOVBR_FAKE_HOST": "fake_host",
    "GOVBR_FAKE_PORT": "fake_port",
    "GOVBR_FAKE_PROVIDER_PREFIX": "fake_provider_prefix",
    "GOVBR_FAKE_CLIENT_ID": "fake_client_id",
    "GOVBR_FAKE_CLIENT_SECRET": "fake_client_secret",
    "GOVBR_FAKE_REDIRECT_URI": "fake_redirect_uri",
    "GOVBR_FAKE_REQUEST_TTL_SECONDS": "fake_request_ttl_seconds",
    "GOVBR_FAKE_AUTHORIZATION_CODE_TTL_SECONDS": "fake_authorization_code_ttl_seconds",
    "GOVBR_FAKE_ACCESS_TOKEN_TTL_SECONDS": "fake_access_token_ttl_seconds",
    "GOVBR_FAKE_ID_TOKEN_TTL_SECONDS": "fake_id_token_ttl_seconds",
    "GOVBR_FAKE_USERS_FILE": "fake_users_file",
}

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
