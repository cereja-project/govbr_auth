"""Framework-neutral configuration and composition for Gov.br runtimes."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlsplit

import httpx

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)

from govbr_auth.core.client import GovBrClient
from govbr_auth.core.settings import GovBrSettings, ProviderEnvironment
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import (
    InMemoryTransactionStore,
    generate_transaction_secret,
)

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeGovBrRuntime, FakeUserRepository


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
        return cls.model_validate(_runtime_values(values))


@dataclass(slots=True)
class GovBrRuntime:
    """Own the client resources created by the framework-neutral runtime."""

    settings: GovBrRuntimeSettings
    client: GovBrClient
    provider: GovBrProvider
    fake: "FakeGovBrRuntime | None"
    _owned_http: httpx.AsyncClient | None
    _closed: bool = False

    @property
    def is_closed(self) -> bool:
        """Return whether this runtime has already completed its lifecycle."""
        return self._closed

    async def __aenter__(self) -> "GovBrRuntime":
        """Enter the runtime lifecycle context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close resources when leaving the runtime lifecycle context."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client created by this runtime exactly once."""
        if not self._closed and self._owned_http is not None:
            await self._owned_http.aclose()
        self._closed = True


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time for runtime collaborators."""
    return datetime.now(UTC)


def create_govbr_runtime(
    settings: GovBrRuntimeSettings,
    *,
    http: httpx.AsyncClient | None = None,
    fake_transport_factory: (
        Callable[["FakeGovBrRuntime"], httpx.AsyncBaseTransport] | None
    ) = None,
    clock: Callable[[], datetime] = utc_now,
    user_repository: "FakeUserRepository | None" = None,
) -> GovBrRuntime:
    """Compose an official or local fake runtime without a web framework."""
    if settings.provider is GovBrProvider.FAKE:
        return _create_fake_consumer_runtime(
            settings,
            http=http,
            fake_transport_factory=fake_transport_factory,
            clock=clock,
            user_repository=user_repository,
        )

    oauth = settings.oauth
    if oauth is None:
        raise ValueError("official runtime requires OAuth settings")

    create_client = _create_client(oauth)
    owned_http = None if http is not None else httpx.AsyncClient()
    client = create_client(http if http is not None else owned_http)
    return GovBrRuntime(
        settings=settings,
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=owned_http,
    )


def _create_fake_consumer_runtime(
    settings: GovBrRuntimeSettings,
    *,
    http: httpx.AsyncClient | None,
    fake_transport_factory: (
        Callable[["FakeGovBrRuntime"], httpx.AsyncBaseTransport] | None
    ),
    clock: Callable[[], datetime],
    user_repository: "FakeUserRepository | None",
) -> GovBrRuntime:
    """Compose the fake provider before allocating its owned HTTP client."""
    if http is not None:
        raise ValueError("fake runtime does not accept an HTTP client")
    if fake_transport_factory is None:
        raise ValueError("fake transport factory is required")

    from govbr_auth.fake.runtime import create_fake_govbr_runtime

    effective_settings = settings
    if not settings.fake_end_to_end:
        values = settings.model_dump()
        values["fake_end_to_end"] = True
        effective_settings = GovBrRuntimeSettings.model_validate(values)
    fake = create_fake_govbr_runtime(
        effective_settings,
        clock=clock,
        user_repository=user_repository,
    )
    oauth = _fake_oauth_settings(fake)
    create_client = _create_client(oauth)
    transport = fake_transport_factory(fake)
    if not isinstance(transport, httpx.AsyncBaseTransport):
        raise TypeError("fake transport factory must return AsyncBaseTransport")
    owned_http = httpx.AsyncClient(transport=transport)
    return GovBrRuntime(
        settings=effective_settings,
        client=create_client(owned_http),
        provider=GovBrProvider.FAKE,
        fake=fake,
        _owned_http=owned_http,
    )


def _fake_oauth_settings(fake: "FakeGovBrRuntime") -> GovBrSettings:
    """Derive consumer settings from the validated fake-provider graph."""
    client = fake.settings.clients[0]
    return GovBrSettings(
        environment=ProviderEnvironment.LOCAL,
        authorization_url=fake.endpoints.authorize,
        token_url=fake.endpoints.token,
        userinfo_url=fake.endpoints.userinfo,
        client_id=client.client_id,
        client_secret=client.client_secret,
        redirect_uri=client.registered_redirect_uris[0],
        transaction_secret=SecretStr(generate_transaction_secret()),
        issuer=fake.endpoints.issuer,
        jwks_url=fake.endpoints.jwks,
    )


def _create_client(
    settings: GovBrSettings,
) -> Callable[[httpx.AsyncClient], GovBrClient]:
    """Prepare the common OAuth client composition used by each provider."""
    transactions = InMemoryTransactionStore(settings.transaction_secret)
    validator = IdTokenValidator(settings=settings)

    def create(http: httpx.AsyncClient) -> GovBrClient:
        return GovBrClient(settings, transactions, validator, http)

    return create


def _runtime_values(environ: Mapping[str, str]) -> dict[str, object]:
    """Select only the environment inputs relevant to the chosen provider."""
    provider = environ.get("GOVBR_PROVIDER", GovBrProvider.OFFICIAL.value)
    values: dict[str, object] = {"provider": provider}

    if provider == GovBrProvider.OFFICIAL.value:
        oauth_values = _prefixed_values(environ, _OFFICIAL_OAUTH_FIELDS)
        if oauth_values:
            values["oauth"] = oauth_values
    elif provider == GovBrProvider.FAKE.value:
        if any(name in environ for name in _OFFICIAL_ENDPOINT_FIELDS):
            raise ValueError(
                "official endpoint variables conflict with fake provider selection"
            )
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
