"""HTTP transport for the OAuth core."""

from collections.abc import Mapping
from typing import NoReturn

import httpx
from pydantic import SecretStr

from govbr_auth.core.errors import ProviderUnavailableError
from govbr_auth.core.settings import GovBrSettings

_PROVIDER_FAILURE_MESSAGE = "Gov.br provider request failed"
_PROVIDER_TIMEOUT_MESSAGE = "Gov.br provider request timed out"


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
