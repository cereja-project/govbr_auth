"""Tests for framework-neutral runtime configuration."""

import pytest
from pydantic import ValidationError

from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings


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
