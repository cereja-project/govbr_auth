"""Characterize the extracted OAuth HTTP boundary."""

import httpx
import pytest

from govbr_auth.core.http import decode_jwks, decode_tokens, decode_userinfo
from govbr_auth.core.models import GovBrUser, TokenSet


def test_decode_tokens_returns_domain_model() -> None:
    response = httpx.Response(
        200,
        json={
            "access_token": "access",
            "id_token": "id",
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": "openid",
        },
    )

    result = decode_tokens(response)

    assert isinstance(result, TokenSet)
    assert result.access_token.get_secret_value() == "access"


def test_decode_userinfo_returns_domain_model() -> None:
    result = decode_userinfo(httpx.Response(200, json={"sub": "subject"}))

    assert isinstance(result, GovBrUser)
    assert result.sub == "subject"


def test_decode_jwks_requires_nonempty_key_mappings() -> None:
    with pytest.raises(Exception, match="JWKS response is invalid"):
        decode_jwks(httpx.Response(200, json={"keys": []}))
