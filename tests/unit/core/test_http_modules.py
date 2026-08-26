"""Tests for the split OAuth transport and decoder modules."""

import httpx

from govbr_auth.core.decoders import decode_tokens
from govbr_auth.core.models import TokenSet
from govbr_auth.core.transport import GovBrHttpTransport


def test_transport_is_exposed_from_the_transport_module() -> None:
    assert GovBrHttpTransport.__module__ == "govbr_auth.core.transport"


def test_token_decoder_is_exposed_from_the_decoders_module() -> None:
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
