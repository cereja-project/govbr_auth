"""HTTP transport and response decoding for the OAuth core."""

import json
from collections.abc import Mapping
from typing import NoReturn

import httpx
from pydantic import SecretStr, ValidationError

from govbr_auth.core.errors import GovBrAuthError, ProviderUnavailableError
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings

_PROVIDER_FAILURE_MESSAGE = "Gov.br provider request failed"
_PROVIDER_TIMEOUT_MESSAGE = "Gov.br provider request timed out"
_TOKEN_RESPONSE_MESSAGE = "Gov.br token response is invalid"
_JWKS_RESPONSE_MESSAGE = "Gov.br JWKS response is invalid"
_USERINFO_RESPONSE_MESSAGE = "Gov.br userinfo response is invalid"


class GovBrHttpTransport:
    """Perform provider requests and normalize transport failures."""

    def __init__(self, settings: GovBrSettings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.read_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        )

    async def post_token(self, form: Mapping[str, str]) -> httpx.Response:
        return await self._request(
            self._http.post,
            str(self._settings.token_url),
            data=form,
            auth=(
                self._settings.client_id,
                self._settings.client_secret.get_secret_value(),
            ),
        )

    async def get_userinfo(self, access_token: SecretStr) -> httpx.Response:
        return await self._request(
            self._http.get,
            str(self._settings.userinfo_url),
            headers={"Authorization": f"Bearer {access_token.get_secret_value()}"},
        )

    async def get_jwks(self) -> httpx.Response:
        return await self._request(self._http.get, str(self._settings.jwks_url))

    async def _request(self, method, url: str, **kwargs) -> httpx.Response:
        try:
            return await method(url, timeout=self._timeout, **kwargs)
        except httpx.TimeoutException as error:
            failure_message = _PROVIDER_TIMEOUT_MESSAGE
            failure_type = type(error).__name__
        except httpx.TransportError as error:
            failure_message = _PROVIDER_FAILURE_MESSAGE
            failure_type = type(error).__name__

        self._raise_transport_error(failure_message, failure_type)

    @staticmethod
    def _raise_transport_error(message: str, failure_type: str) -> NoReturn:
        safe_cause = RuntimeError(f"Gov.br HTTP transport failed ({failure_type})")
        raise ProviderUnavailableError(message) from safe_cause


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
