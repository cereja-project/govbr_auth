"""OAuth and OIDC response decoders for the framework-neutral core."""

import json
from collections.abc import Mapping
from typing import NoReturn

import httpx
from pydantic import ValidationError

from govbr_auth.core.errors import GovBrAuthError
from govbr_auth.core.models import GovBrUser, TokenSet

_TOKEN_RESPONSE_MESSAGE = "Gov.br token response is invalid"
_JWKS_RESPONSE_MESSAGE = "Gov.br JWKS response is invalid"
_USERINFO_RESPONSE_MESSAGE = "Gov.br userinfo response is invalid"


def decode_tokens(response: httpx.Response) -> TokenSet:
    """Decode and validate an OAuth token response."""
    try:
        return TokenSet.model_validate(response.json())
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as error:
        failure_type = type(error).__name__
    _raise_invalid_response(_TOKEN_RESPONSE_MESSAGE, failure_type)


def decode_userinfo(response: httpx.Response) -> GovBrUser:
    """Decode and validate an OIDC userinfo response."""
    try:
        return GovBrUser.model_validate(response.json())
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as error:
        failure_type = type(error).__name__
    _raise_invalid_response(_USERINFO_RESPONSE_MESSAGE, failure_type)


def decode_jwks(response: httpx.Response) -> Mapping[str, object]:
    """Decode the minimal JWKS shape required by the token validator."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        failure_type = type(error).__name__
    else:
        if isinstance(payload, Mapping):
            keys = payload.get("keys")
            if (
                isinstance(keys, list)
                and keys
                and all(isinstance(key, Mapping) and key for key in keys)
            ):
                return {"keys": [dict(key) for key in keys]}
        failure_type = "InvalidJwks"

    _raise_invalid_response(_JWKS_RESPONSE_MESSAGE, failure_type)


def _raise_invalid_response(message: str, failure_type: str) -> NoReturn:
    safe_cause = ValueError(f"Gov.br response validation failed ({failure_type})")
    raise GovBrAuthError(message) from safe_cause
