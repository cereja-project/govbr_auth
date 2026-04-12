import pytest

from govbr_auth.core.config import GovBrConfig


def test_govbr_config_instantiation_without_optional_endpoints_does_not_raise_attribute_error():
    config = GovBrConfig(
        client_id="dummy_id",
        client_secret="dummy_secret",
        govbr_auth_url="https://localhost/authorize",
        govbr_token_url="https://localhost/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso=",
    )

    assert config.prefix is None
    assert config.authorize_endpoint is None
    assert config.authenticate_endpoint is None


def test_govbr_config_instantiation_with_optional_endpoints_strips_slashes():
    config = GovBrConfig(
        client_id="dummy_id",
        client_secret="dummy_secret",
        govbr_auth_url="https://localhost/authorize",
        govbr_token_url="https://localhost/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso=",
        prefix="/auth/",
        authorize_endpoint="/govbr/authorize/",
        authenticate_endpoint="/govbr/callback/",
    )

    assert config.prefix == "auth"
    assert config.authorize_endpoint == "govbr/authorize"
    assert config.authenticate_endpoint == "govbr/callback"

