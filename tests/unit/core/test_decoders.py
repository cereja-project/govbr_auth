"""Focused tests for the extracted OAuth response decoders."""

import httpx
import pytest

from govbr_auth.core.decoders import decode_jwks, decode_tokens, decode_userinfo
from govbr_auth.core.errors import GovBrAuthError
from govbr_auth.core.models import GovBrUser, TokenSet


def test_decode_tokens_returns_domain_model_from_split_module() -> None:
    result = decode_tokens(
        httpx.Response(
            200,
            json={
                "access_token": "access",
                "id_token": "id",
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "openid",
            },
        )
    )

    assert isinstance(result, TokenSet)
    assert result.access_token.get_secret_value() == "access"


def test_decode_userinfo_returns_domain_model_from_split_module() -> None:
    result = decode_userinfo(httpx.Response(200, json={"sub": "subject"}))

    assert isinstance(result, GovBrUser)
    assert result.sub == "subject"


def test_decode_jwks_returns_independent_key_mappings() -> None:
    payload = {"keys": [{"kid": "provider-key"}]}

    result = decode_jwks(httpx.Response(200, json=payload))

    assert result == payload
    assert result["keys"] is not payload["keys"]


def test_decode_jwks_rejects_empty_key_mappings() -> None:
    with pytest.raises(GovBrAuthError, match="JWKS response is invalid"):
        decode_jwks(httpx.Response(200, json={"keys": []}))
