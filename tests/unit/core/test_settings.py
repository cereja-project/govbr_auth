"""Tests for strict Gov.br provider configuration."""

import pytest
from pydantic import ValidationError

from govbr_auth.core.settings import GovBrSettings, ProviderEnvironment


@pytest.fixture
def valid_settings_data() -> dict[str, object]:
    return {
        "authorization_url": "https://sso.acesso.gov.br/authorize",
        "token_url": "https://sso.acesso.gov.br/token",
        "userinfo_url": "https://sso.acesso.gov.br/userinfo",
        "client_id": "test-client",
        "client_secret": "test-client-secret",
        "redirect_uri": "https://consumer.example.test/oauth/callback",
        "scope": "openid profile email",
        "transaction_secret": "test-transaction-secret",
        "issuer": "https://sso.acesso.gov.br",
        "jwks_url": "https://sso.acesso.gov.br/jwk",
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 10,
        "clock_skew_seconds": 60,
    }


def test_production_rejects_non_https_provider_url(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["authorization_url"] = "http://sso.acesso.gov.br/authorize"

    with pytest.raises(ValidationError, match="https"):
        GovBrSettings(**valid_settings_data)


def test_local_environment_accepts_loopback_http(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.LOCAL
    valid_settings_data["authorization_url"] = (
        "http://127.0.0.1:8000/fake-govbr/authorize"
    )

    settings = GovBrSettings(**valid_settings_data)

    assert settings.environment is ProviderEnvironment.LOCAL


def test_local_environment_rejects_http_for_non_loopback_provider_url(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["authorization_url"] = "http://sso.acesso.gov.br/authorize"

    with pytest.raises(ValidationError, match="loopback"):
        GovBrSettings(**valid_settings_data, environment=ProviderEnvironment.LOCAL)


def test_local_environment_accepts_ipv6_loopback_http(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.LOCAL
    valid_settings_data["authorization_url"] = "http://[::1]:8000/fake-govbr/authorize"

    settings = GovBrSettings(**valid_settings_data)

    assert str(settings.authorization_url) == "http://[::1]:8000/fake-govbr/authorize"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        pytest.param("client_id", "   ", id="blank_client_id"),
        pytest.param("client_secret", "   ", id="blank_client_secret"),
        pytest.param("transaction_secret", "   ", id="blank_transaction_secret"),
        pytest.param("scope", "   ", id="blank_scope"),
    ],
)
def test_settings_rejects_blank_security_critical_values(
    valid_settings_data: dict[str, object], field_name: str, value: str
) -> None:
    valid_settings_data[field_name] = value

    with pytest.raises(ValidationError, match="must not be empty"):
        GovBrSettings(**valid_settings_data)


def test_settings_rejects_unknown_configuration(
    valid_settings_data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        GovBrSettings(**valid_settings_data, unexpected="value")
