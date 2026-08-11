"""Caracteriza o contrato de token HTTP da versão 0.2.2."""

import hmac
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from cryptography.fernet import Fernet

from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration


@pytest.mark.asyncio
async def test_async_exchange_code_for_token_envia_o_wire_contract_v022():
    fixture_path = Path(__file__).parent / "fixtures" / "govbr_token_success.json"
    token_response = json.loads(fixture_path.read_text(encoding="utf-8"))
    config = GovBrConfig(
        client_id="contract-client",
        client_secret="contract-client-secret",
        redirect_uri="https://consumer.example.test/oauth/callback",
        cript_verifier_secret="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        govbr_auth_url="https://sso.example.test/authorize",
        govbr_token_url="https://sso.example.test/token",
        jwt_secret="sanitized-test-jwt-signing-secret-0123456789",
    )
    authorization = GovBrAuthorize(config).build_authorize_url()
    state = parse_qs(urlparse(authorization["url"]).query, strict_parsing=True)[
        "state"
    ][0]
    expected_code_verifier = (
        Fernet(config.cript_verifier_secret.encode("utf-8"))
        .decrypt(state.encode("utf-8"))
        .decode("utf-8")
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.post(config.govbr_token_url).mock(
            return_value=httpx.Response(200, json=token_response)
        )

        token_data = await GovBrIntegration(config).async_exchange_code_for_token(
            code="sanitized-authorization-code",
            state=state,
        )

    assert len(route.calls) == 1

    request = route.calls[0].request
    request_form = parse_qs(request.content.decode("utf-8"), strict_parsing=True)
    request_code_verifier = request_form.pop("code_verifier")

    assert token_data["token"] == token_response
    assert token_data["id_token_decoded"] == {
        "sub": "sanitized-subject",
        "iss": "https://sso.example.test",
        "exp": 4102444800,
        "iat": 1704067200,
        "nonce": "sanitized-nonce",
    }
    assert request.method == "POST"
    assert request.url == httpx.URL("https://sso.example.test/token")
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert (
        request.headers["authorization"]
        == "Basic Y29udHJhY3QtY2xpZW50OmNvbnRyYWN0LWNsaWVudC1zZWNyZXQ="
    )
    assert request_form == {
        "grant_type": ["authorization_code"],
        "code": ["sanitized-authorization-code"],
        "redirect_uri": ["https://consumer.example.test/oauth/callback"],
    }
    assert hmac.compare_digest(request_code_verifier[0], expected_code_verifier)
