"""Tests for framework-neutral runtime configuration and lifecycle."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

import govbr_auth.runtime as runtime_module
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntimeSettings,
    create_govbr_runtime,
    utc_now,
)


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runtime configuration tests independent from dotenv-loading tests."""
    for variable in (
        "GOVBR_PROVIDER",
        "GOVBR_ENVIRONMENT",
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_CLIENT_ID",
        "GOVBR_CLIENT_SECRET",
        "GOVBR_REDIRECT_URI",
        "GOVBR_SCOPE",
        "GOVBR_TRANSACTION_SECRET",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
        "GOVBR_CONNECT_TIMEOUT_SECONDS",
        "GOVBR_READ_TIMEOUT_SECONDS",
        "GOVBR_CLOCK_SKEW_SECONDS",
        "GOVBR_FAKE_END_TO_END",
        "GOVBR_FAKE_HOST",
        "GOVBR_FAKE_PORT",
        "GOVBR_FAKE_PROVIDER_PREFIX",
        "GOVBR_FAKE_CLIENT_ID",
        "GOVBR_FAKE_CLIENT_SECRET",
        "GOVBR_FAKE_REDIRECT_URI",
        "GOVBR_FAKE_REQUEST_TTL_SECONDS",
        "GOVBR_FAKE_AUTHORIZATION_CODE_TTL_SECONDS",
        "GOVBR_FAKE_ACCESS_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_ID_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_USERS_FILE",
    ):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def settings() -> GovBrRuntimeSettings:
    """Provide complete official settings for runtime composition."""
    return GovBrRuntimeSettings(
        oauth=GovBrSettings(
            authorization_url="https://sso.example.test/authorize",
            token_url="https://sso.example.test/token",
            userinfo_url="https://sso.example.test/userinfo",
            client_id="test-client",
            client_secret=SecretStr("test-client-secret"),
            redirect_uri="https://consumer.example.test/oauth/callback",
            transaction_secret=SecretStr(Fernet.generate_key().decode("ascii")),
            issuer="https://sso.example.test",
            jwks_url="https://sso.example.test/jwks",
        )
    )


@pytest.fixture
def fake_settings() -> GovBrRuntimeSettings:
    """Provide complete settings for an embedded fake provider."""
    return GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_end_to_end=True,
        fake_redirect_uri="http://127.0.0.1:8000/auth/govbr/callback",
    )


def test_runtime_settings_default_to_official(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime must not enable the fake provider implicitly."""
    monkeypatch.delenv("GOVBR_PROVIDER", raising=False)

    settings = GovBrRuntimeSettings.from_environment()

    assert settings.provider is GovBrProvider.OFFICIAL


def test_runtime_settings_select_fake_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit fake provider selection must reach the runtime boundary."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")

    settings = GovBrRuntimeSettings.from_environment()

    assert settings.provider is GovBrProvider.FAKE


def test_runtime_settings_parse_explicit_false_end_to_end() -> None:
    """The canonical false spelling must keep the provider-only profile."""
    settings = GovBrRuntimeSettings.from_environment(
        {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_END_TO_END": "false"}
    )

    assert settings.fake_end_to_end is False


def test_runtime_settings_build_official_oauth_from_environment() -> None:
    """Official environment fields must populate the nested OAuth settings."""
    settings = GovBrRuntimeSettings.from_environment(
        {
            "GOVBR_AUTHORIZATION_URL": "https://sso.example.test/authorize",
            "GOVBR_TOKEN_URL": "https://sso.example.test/token",
            "GOVBR_USERINFO_URL": "https://sso.example.test/userinfo",
            "GOVBR_CLIENT_ID": "test-client",
            "GOVBR_CLIENT_SECRET": "test-client-secret",
            "GOVBR_REDIRECT_URI": "https://consumer.example.test/oauth/callback",
            "GOVBR_TRANSACTION_SECRET": Fernet.generate_key().decode("ascii"),
            "GOVBR_ISSUER": "https://sso.example.test",
            "GOVBR_JWKS_URL": "https://sso.example.test/jwks",
        }
    )

    assert settings.oauth is not None
    assert settings.oauth.client_id == "test-client"


def test_runtime_settings_reject_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported providers must fail before runtime construction."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fallback")

    with pytest.raises(ValidationError):
        GovBrRuntimeSettings.from_environment()


@pytest.mark.parametrize(
    "variable",
    (
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ),
    ids=("authorize", "token", "userinfo", "redirect", "issuer", "jwks"),
)
def test_fake_environment_rejects_official_endpoint_variables(variable: str) -> None:
    """Fake selection must not silently ignore an official provider endpoint."""
    with pytest.raises(ValueError, match="official endpoint"):
        GovBrRuntimeSettings.from_environment(
            {
                "GOVBR_PROVIDER": "fake",
                variable: "https://sso.example.test/endpoint",
            }
        )


def test_runtime_configuration_is_available_from_core() -> None:
    """Core consumers must have one framework-neutral runtime configuration API."""
    from govbr_auth.core import GovBrProvider as CoreGovBrProvider
    from govbr_auth.core import GovBrRuntimeSettings as CoreGovBrRuntimeSettings

    assert CoreGovBrProvider is GovBrProvider
    assert CoreGovBrRuntimeSettings is GovBrRuntimeSettings


@pytest.mark.parametrize("value", ["1", "yes", "enabled", ""])
def test_runtime_settings_reject_noncanonical_end_to_end(value: str) -> None:
    """Truth-like strings must not accidentally activate the fake flow."""
    with pytest.raises(ValidationError):
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_END_TO_END": value}
        )


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "example.test"])
def test_runtime_settings_reject_non_loopback_fake_host(host: str) -> None:
    """The local fake provider must not bind a remotely reachable host."""
    with pytest.raises(ValidationError):
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_HOST": host}
        )


@pytest.mark.parametrize("port", ["0", "65536"])
def test_runtime_settings_reject_invalid_fake_port(port: str) -> None:
    """The runtime must reject ports outside the TCP port range."""
    with pytest.raises(ValidationError):
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_PORT": port}
        )


@pytest.mark.parametrize(
    "prefix",
    (
        "",
        "   ",
        "fake-govbr",
        "/",
        "/fake-govbr/",
        "/fake-govbr?debug=1",
        "/fake-govbr#fragment",
        "https://example.test/fake-govbr",
        "//example.test/fake-govbr",
    ),
    ids=(
        "empty",
        "whitespace",
        "missing-leading-slash",
        "root",
        "trailing-slash",
        "query",
        "fragment",
        "absolute-url",
        "network-path",
    ),
)
def test_end_to_end_settings_reject_invalid_fake_provider_prefix(
    prefix: str,
) -> None:
    """Mounted fake routes require one unambiguous non-root path prefix."""
    with pytest.raises(ValidationError, match="fake provider prefix"):
        GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
            fake_provider_prefix=prefix,
        )


def test_embedded_runtime_revalidates_fake_provider_prefix() -> None:
    """Consumer embedding must validate a prefix unused by provider-only mode."""
    settings = GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_provider_prefix="//example.test/fake-govbr",
    )

    def fail_if_factory_called(_):
        raise AssertionError("invalid prefix must fail before transport composition")

    with pytest.raises(ValidationError, match="fake provider prefix"):
        create_govbr_runtime(
            settings,
            fake_transport_factory=fail_if_factory_called,
        )


def test_official_runtime_rejects_unvalidated_settings_without_oauth() -> None:
    """Runtime composition must retain its defensive OAuth invariant."""
    settings = GovBrRuntimeSettings.model_construct(
        provider=GovBrProvider.OFFICIAL,
        oauth=None,
    )

    with pytest.raises(ValueError, match="official runtime requires OAuth settings"):
        create_govbr_runtime(settings)


@pytest.mark.asyncio
async def test_official_runtime_owns_and_closes_created_http_client(
    settings: GovBrRuntimeSettings,
) -> None:
    """A runtime-created HTTP client must be closed with its runtime."""
    runtime = create_govbr_runtime(settings)

    assert runtime.provider is GovBrProvider.OFFICIAL
    assert runtime.fake is None

    await runtime.aclose()

    assert runtime.is_closed is True


@pytest.mark.asyncio
async def test_runtime_does_not_close_injected_http_client(
    settings: GovBrRuntimeSettings,
) -> None:
    """A caller-owned HTTP client must remain usable after runtime closure."""
    async with httpx.AsyncClient() as http:
        runtime = create_govbr_runtime(settings, http=http)

        await runtime.aclose()

        assert http.is_closed is False


@pytest.mark.asyncio
async def test_runtime_context_closes_owned_resources(
    settings: GovBrRuntimeSettings,
) -> None:
    """Leaving a runtime context must complete its owned-resource lifecycle."""
    async with create_govbr_runtime(settings) as runtime:
        assert runtime.is_closed is False

    assert runtime.is_closed is True


@pytest.mark.asyncio
async def test_runtime_closes_an_owned_http_client_only_once(
    settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated closure must not close a runtime-owned client more than once."""

    class CountingAsyncClient(httpx.AsyncClient):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1
            await super().aclose()

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", CountingAsyncClient)
    runtime = create_govbr_runtime(settings)
    owned_http = runtime.client._http

    await runtime.aclose()
    await runtime.aclose()

    assert isinstance(owned_http, CountingAsyncClient)
    assert owned_http.close_calls == 1


def test_official_runtime_validates_dependencies_before_creating_owned_http(
    settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid transaction encryption must not allocate a client to leak."""
    assert settings.oauth is not None
    invalid_settings = settings.model_copy(
        update={
            "oauth": settings.oauth.model_copy(
                update={"transaction_secret": SecretStr("invalid-fernet-key")}
            )
        }
    )
    http_created = False

    def fail_if_http_created() -> httpx.AsyncClient:
        nonlocal http_created
        http_created = True
        raise AssertionError("the owned HTTP client must not be created")

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fail_if_http_created)

    with pytest.raises(ValueError):
        create_govbr_runtime(invalid_settings)

    assert http_created is False


def test_fake_runtime_uses_its_exact_endpoint_set(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Consumer settings must be derived from the composed fake provider."""
    supplied_fake = None

    def transport_factory(fake):
        nonlocal supplied_fake
        supplied_fake = fake
        return httpx.MockTransport(lambda _: httpx.Response(500))

    runtime = create_govbr_runtime(
        fake_settings,
        fake_transport_factory=transport_factory,
        clock=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert runtime.fake is supplied_fake
    assert runtime.fake is not None
    assert (
        str(runtime.client._settings.authorization_url)
        == runtime.fake.endpoints.authorize
    )
    assert str(runtime.client._settings.token_url) == runtime.fake.endpoints.token
    assert str(runtime.client._settings.userinfo_url) == runtime.fake.endpoints.userinfo
    assert str(runtime.client._settings.jwks_url) == runtime.fake.endpoints.jwks
    assert str(runtime.client._settings.issuer) == runtime.fake.endpoints.issuer


def test_fake_consumer_runtime_mounts_provider_below_configured_prefix(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Embedded consumers must not collide with application root routes."""
    provider_only_settings = fake_settings.model_copy(update={"fake_end_to_end": False})

    runtime = create_govbr_runtime(
        provider_only_settings,
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda __: httpx.Response(500)
        ),
    )

    assert runtime.fake is not None
    assert runtime.fake.prefix == provider_only_settings.fake_provider_prefix
    assert runtime.fake.endpoints.authorize.endswith("/fake-govbr/authorize")


def test_fake_runtime_requires_transport_factory_before_allocating_http(
    fake_settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ASGI composition must fail without leaking an HTTP client."""
    http_created = False

    def fail_if_http_created(*args: object, **kwargs: object) -> httpx.AsyncClient:
        nonlocal http_created
        http_created = True
        raise AssertionError("the owned HTTP client must not be created")

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fail_if_http_created)

    with pytest.raises(ValueError, match="fake transport factory"):
        create_govbr_runtime(fake_settings)

    assert http_created is False


@pytest.mark.asyncio
async def test_fake_runtime_rejects_injected_http_instead_of_transport_factory(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Fake composition must let the adapter receive the composed provider."""
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError, match="does not accept an HTTP client"):
            create_govbr_runtime(
                fake_settings,
                http=http,
                fake_transport_factory=lambda _: httpx.MockTransport(
                    lambda __: httpx.Response(500)
                ),
            )


def test_fake_runtime_validates_transport_before_allocating_http(
    fake_settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid adapter result must fail before an HTTP client is owned."""
    http_created = False

    def fail_if_http_created(*args: object, **kwargs: object) -> httpx.AsyncClient:
        nonlocal http_created
        http_created = True
        raise AssertionError("the owned HTTP client must not be created")

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fail_if_http_created)

    with pytest.raises(TypeError, match="AsyncBaseTransport"):
        create_govbr_runtime(
            fake_settings,
            fake_transport_factory=lambda _: object(),
        )

    assert http_created is False


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    """Runtime clocks must supply an aware datetime in the UTC timezone."""
    current_time = utc_now()

    assert current_time.tzinfo is UTC
    assert current_time.utcoffset().total_seconds() == 0


def test_runtime_source_has_no_web_framework_imports() -> None:
    """Runtime composition must remain usable without a web framework."""
    source = Path("govbr_auth/runtime.py").read_text(encoding="utf-8")

    assert all(
        name not in source for name in ("fastapi", "starlette", "flask", "django")
    )
