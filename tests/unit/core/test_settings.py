"""Tests for strict Gov.br provider configuration."""

import pytest
from pydantic import ValidationError

from govbr_auth.core.settings import GovBrSettings, ProviderEnvironment


def _use_local_provider_urls(settings_data: dict[str, object]) -> None:
    settings_data.update(
        {
            "authorization_url": "http://127.0.0.1:8000/authorize",
            "token_url": "http://127.0.0.1:8000/token",
            "userinfo_url": "http://127.0.0.1:8000/userinfo",
            "issuer": "http://127.0.0.1:8000",
            "jwks_url": "http://127.0.0.1:8000/jwk",
        }
    )


def _use_staging_provider_urls(settings_data: dict[str, object]) -> None:
    settings_data.update(
        {
            "authorization_url": "https://sso.staging.acesso.gov.br/authorize",
            "token_url": "https://sso.staging.acesso.gov.br/token",
            "userinfo_url": "https://sso.staging.acesso.gov.br/userinfo/",
            "issuer": "https://sso.staging.acesso.gov.br/",
            "jwks_url": "https://sso.staging.acesso.gov.br/jwk",
        }
    )


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

    with pytest.raises(ValidationError) as exc_info:
        GovBrSettings(**valid_settings_data)

    message = str(exc_info.value)
    assert "GOVBR_AUTHORIZATION_URL usa HTTP em um host não-loopback" in message
    assert "Configure HTTPS" in message
    assert "sso.acesso.gov.br" not in message


def test_local_environment_accepts_loopback_http(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.LOCAL
    _use_local_provider_urls(valid_settings_data)

    settings = GovBrSettings(**valid_settings_data)

    assert settings.environment is ProviderEnvironment.LOCAL


def test_local_environment_rejects_http_for_non_loopback_provider_url(
    valid_settings_data: dict[str, object],
) -> None:
    _use_local_provider_urls(valid_settings_data)
    valid_settings_data["authorization_url"] = "http://sso.acesso.gov.br/authorize"

    with pytest.raises(ValidationError, match="loopback"):
        GovBrSettings(**valid_settings_data, environment=ProviderEnvironment.LOCAL)


def test_local_environment_accepts_ipv6_loopback_http(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.LOCAL
    _use_local_provider_urls(valid_settings_data)
    valid_settings_data["authorization_url"] = "http://[::1]:8000/fake-govbr/authorize"

    settings = GovBrSettings(**valid_settings_data)

    assert str(settings.authorization_url) == "http://[::1]:8000/fake-govbr/authorize"


def test_staging_rejects_production_validation_endpoints(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.STAGING
    _use_staging_provider_urls(valid_settings_data)
    valid_settings_data["issuer"] = "https://sso.acesso.gov.br/"
    valid_settings_data["jwks_url"] = "https://sso.acesso.gov.br/jwk"

    with pytest.raises(ValidationError) as exc_info:
        GovBrSettings(**valid_settings_data)

    message = str(exc_info.value)
    assert "GOVBR_ISSUER" in message
    assert "GOVBR_JWKS_URL" in message
    assert "staging" in message
    assert "sso.staging.acesso.gov.br" not in message
    assert "sso.acesso.gov.br" not in message
    assert "test-client-secret" not in message


def test_local_rejects_remote_official_govbr_endpoints(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.LOCAL

    with pytest.raises(ValidationError, match="GOVBR_ENVIRONMENT.*local"):
        GovBrSettings(**valid_settings_data)


def test_environment_mismatch_hides_configured_values_in_error() -> None:
    sensitive_url = "https://sso.acesso.gov.br/private-jwks-marker"
    sensitive_secret = "sensitive-secret-marker"
    settings_data = {
        "environment": ProviderEnvironment.STAGING,
        "authorization_url": "https://sso.staging.acesso.gov.br/authorize",
        "token_url": "https://sso.staging.acesso.gov.br/token",
        "userinfo_url": "https://sso.staging.acesso.gov.br/userinfo/",
        "client_id": "test-client",
        "redirect_uri": "https://consumer.example.test/oauth/callback",
        "issuer": "https://sso.staging.acesso.gov.br/",
        "jwks_url": sensitive_url,
        "client_secret": sensitive_secret,
        "transaction_secret": sensitive_secret,
    }

    with pytest.raises(ValidationError) as exc_info:
        GovBrSettings(**settings_data)

    message = str(exc_info.value)
    assert sensitive_url not in message
    assert "secret-marker" not in message


def test_staging_accepts_matching_official_govbr_endpoints(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.STAGING
    _use_staging_provider_urls(valid_settings_data)

    settings = GovBrSettings(**valid_settings_data)

    assert settings.environment is ProviderEnvironment.STAGING


def test_staging_accepts_loopback_http_redirect_uri(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.STAGING
    _use_staging_provider_urls(valid_settings_data)
    valid_settings_data["redirect_uri"] = "http://127.0.0.1:8000/oauth/callback"

    settings = GovBrSettings(**valid_settings_data)

    assert str(settings.redirect_uri) == "http://127.0.0.1:8000/oauth/callback"


def test_production_rejects_staging_official_govbr_endpoints(
    valid_settings_data: dict[str, object],
) -> None:
    _use_staging_provider_urls(valid_settings_data)

    with pytest.raises(ValidationError, match="GOVBR_ENVIRONMENT.*production"):
        GovBrSettings(**valid_settings_data)


def test_staging_rejects_production_official_host_with_trailing_dot(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["environment"] = ProviderEnvironment.STAGING
    _use_staging_provider_urls(valid_settings_data)
    valid_settings_data["token_url"] = "https://sso.acesso.gov.br./token"

    with pytest.raises(ValidationError, match="GOVBR_TOKEN_URL"):
        GovBrSettings(**valid_settings_data)


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


@pytest.mark.parametrize(
    "field_name",
    ("logout_url", "post_logout_redirect_uri"),
)
def test_settings_rejects_partial_logout_configuration(
    valid_settings_data: dict[str, object], field_name: str
) -> None:
    valid_settings_data[field_name] = "https://sso.example.test/logout"

    with pytest.raises(ValidationError, match="logout"):
        GovBrSettings(**valid_settings_data)


def test_settings_rejects_non_https_logout_endpoint(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data.update(
        {
            "logout_url": "http://logout.example.test/logout",
            "post_logout_redirect_uri": "https://consumer.example.test/signed-out",
        }
    )

    with pytest.raises(ValidationError, match="GOVBR_LOGOUT_URL"):
        GovBrSettings(**valid_settings_data)
