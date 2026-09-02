"""Validated, framework-neutral runtime configuration."""

import os
import re
import warnings
from collections.abc import Collection, Mapping
from pathlib import Path
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    PositiveInt,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from govbr_auth.core.settings import GovBrSettings


class GovBrProvider(StrEnum):
    """Select the provider used by a runtime composition root."""

    OFFICIAL = "official"
    FAKE = "fake"


class GovBrRuntimeSettings(BaseModel):
    """Keep provider selection and runtime inputs independent of web frameworks."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

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

    @model_validator(mode="after")
    def validate_mounted_fake_provider_prefix(self) -> "GovBrRuntimeSettings":
        """Require one unambiguous path prefix when fake routes are mounted."""
        if not self.fake_end_to_end:
            return self
        prefix = self.fake_provider_prefix
        if not _is_canonical_path_prefix(prefix):
            raise ValueError(
                "fake provider prefix must be a non-root path without a trailing "
                "slash, query, fragment, or absolute URL"
            )
        return self

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "GovBrRuntimeSettings":
        """Build validated settings from an explicit environment mapping."""
        values = os.environ if environ is None else environ
        try:
            return cls.model_validate(_runtime_values(values))
        except ValidationError as error:
            raise ValueError(_configuration_error_message(error)) from None


def _runtime_values(environ: Mapping[str, str]) -> dict[str, object]:
    """Select only the environment inputs relevant to the chosen provider."""
    _reject_unknown_govbr_variables(environ)
    provider = environ.get("GOVBR_PROVIDER", GovBrProvider.OFFICIAL.value)
    values: dict[str, object] = {"provider": provider}

    if provider == GovBrProvider.OFFICIAL.value:
        _warn_about_inactive_variables(
            environ,
            provider=provider,
            inactive_variables=_FAKE_FIELDS,
        )
        oauth_values = _prefixed_values(environ, _OFFICIAL_OAUTH_FIELDS)
        if oauth_values:
            values["oauth"] = oauth_values
    elif provider == GovBrProvider.FAKE.value:
        conflicting_endpoints = sorted(
            set(environ).intersection(_OFFICIAL_ENDPOINT_FIELDS)
        )
        if conflicting_endpoints:
            raise ValueError(
                "official endpoint variable(s) conflict with fake provider "
                "selection: " + ", ".join(conflicting_endpoints)
            )
        _warn_about_inactive_variables(
            environ,
            provider=provider,
            inactive_variables=(
                _OFFICIAL_OAUTH_FIELDS.keys() - _OFFICIAL_ENDPOINT_FIELDS
            ),
        )
        values.update(_prefixed_values(environ, _FAKE_FIELDS))
        if (
            values.get("fake_end_to_end") == "true"
            and "fake_redirect_uri" not in values
        ):
            values["fake_redirect_uri"] = _default_fake_redirect_uri(values)

    return values


def _configuration_error_message(error: ValidationError) -> str:
    """Translate validation failures without exposing configured values."""
    details = [
        _configuration_issue_message(issue)
        for issue in error.errors(include_url=False, include_input=False)
    ]
    unique_details = list(dict.fromkeys(details))
    return "Configuração Gov.br inválida: " + "; ".join(unique_details) + "."


def _configuration_issue_message(issue: Mapping[str, object]) -> str:
    """Describe one Pydantic issue in concise Brazilian Portuguese."""
    context = issue.get("ctx")
    if isinstance(context, Mapping):
        custom_error = context.get("error")
        detail = str(custom_error) if custom_error is not None else ""
        if detail.startswith(("Endpoints oficiais do Gov.br", "GOVBR_")):
            return detail

    location = issue.get("loc")
    field_name = location[-1] if isinstance(location, tuple) and location else None
    environment_name = _ENVIRONMENT_NAMES_BY_FIELD.get(field_name)
    if environment_name is None:
        return "combinação de valores inválida"
    if issue.get("type") == "missing":
        return f"variável obrigatória ausente: {environment_name}"
    return f"valor inválido para {environment_name}"


def _reject_unknown_govbr_variables(environ: Mapping[str, str]) -> None:
    """Reject misspelled or unsupported configuration instead of defaulting."""
    unknown = sorted(
        name
        for name in environ
        if name.startswith("GOVBR_") and name not in _KNOWN_ENVIRONMENT_VARIABLES
    )
    if unknown:
        raise ValueError(
            "unknown GOVBR configuration variable(s): " + ", ".join(unknown)
        )


def _warn_about_inactive_variables(
    environ: Mapping[str, str],
    *,
    provider: str,
    inactive_variables: Collection[str],
) -> None:
    """Identify recognized settings ignored for the selected provider."""
    inactive = sorted(set(environ).intersection(inactive_variables))
    if inactive:
        warnings.warn(
            "ignoring provider-inactive GOVBR configuration variable(s) for "
            f"provider '{provider}': {', '.join(inactive)}",
            UserWarning,
            stacklevel=4,
        )


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
    return _fake_callback_url(host, values.get("fake_port", 8000), "/auth/govbr")


def _fake_callback_url(host: object, port: object, prefix: str) -> str:
    """Build the local consumer callback shared by settings and adapters."""
    rendered_host = f"[{host}]" if host == "::1" else host
    return f"http://{rendered_host}:{port}{prefix}/callback"


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

_OFFICIAL_ENDPOINT_FIELDS = frozenset(
    {
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    }
)

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

_KNOWN_ENVIRONMENT_VARIABLES = frozenset(
    {"GOVBR_PROVIDER", *_OFFICIAL_OAUTH_FIELDS, *_FAKE_FIELDS}
)
_ENVIRONMENT_NAMES_BY_FIELD = {
    "provider": "GOVBR_PROVIDER",
    "demo_page": "GOVBR_DEMO_PAGE",
    **{field_name: name for name, field_name in _OFFICIAL_OAUTH_FIELDS.items()},
    **{field_name: name for name, field_name in _FAKE_FIELDS.items()},
}


def _is_canonical_path_prefix(prefix: str, *, allow_empty: bool = False) -> bool:
    """Return whether a route prefix identifies one unambiguous path."""
    if allow_empty and prefix == "":
        return True
    parsed = urlsplit(prefix)
    segments = prefix[1:].split("/")
    return not (
        not prefix.startswith("/")
        or prefix == "/"
        or prefix.endswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path != prefix
        or not prefix.isascii()
        or any(
            segment in {"", ".", ".."}
            or _FAKE_PREFIX_SEGMENT.fullmatch(segment) is None
            for segment in segments
        )
    )


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_FAKE_PREFIX_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")
