"""Tests for framework-neutral runtime configuration and lifecycle."""

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


def test_runtime_settings_reject_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported providers must fail before runtime construction."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fallback")

    with pytest.raises(ValidationError):
        GovBrRuntimeSettings.from_environment()


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


def test_runtime_source_has_no_web_framework_imports() -> None:
    """Runtime composition must remain usable without a web framework."""
    source = Path("govbr_auth/runtime.py").read_text(encoding="utf-8")

    assert all(
        name not in source for name in ("fastapi", "starlette", "flask", "django")
    )
