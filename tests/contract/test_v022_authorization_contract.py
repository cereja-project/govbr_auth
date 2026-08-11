"""Caracteriza o contrato de autorização HTTP da versão 0.2.2."""

from urllib.parse import parse_qs, urlparse

from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrAuthorize


def test_build_authorize_url_preserva_os_parametros_oauth_e_pkce_v022():
    config = GovBrConfig(
        client_id="contract-client",
        client_secret="contract-client-secret",
        redirect_uri="https://consumer.example.test/oauth/callback",
        cript_verifier_secret="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        govbr_auth_url="https://sso.example.test/authorize",
        govbr_token_url="https://sso.example.test/token",
    )

    authorization = GovBrAuthorize(config).build_authorize_url()

    parsed_url = urlparse(authorization["url"])
    parameters = parse_qs(parsed_url.query, strict_parsing=True)

    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "sso.example.test"
    assert parsed_url.path == "/authorize"
    assert set(parameters) == {
        "response_type",
        "client_id",
        "scope",
        "redirect_uri",
        "nonce",
        "state",
        "code_challenge",
        "code_challenge_method",
    }
    assert parameters["response_type"] == ["code"]
    assert parameters["client_id"] == ["contract-client"]
    assert parameters["scope"] == ["openid profile email"]
    assert parameters["redirect_uri"] == [
        "https://consumer.example.test/oauth/callback"
    ]
    assert len(parameters["nonce"][0]) >= 32
    assert len(parameters["state"][0]) > 0
    assert len(parameters["code_challenge"][0]) == 43
    assert parameters["code_challenge_method"] == ["S256"]
