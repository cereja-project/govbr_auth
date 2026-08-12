"""Asynchronous HTTP orchestration for the strict Gov.br OAuth core."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import NoReturn

import httpx
from pydantic import SecretStr, ValidationError

from govbr_auth.core.authorization import AuthorizationBuilder, AuthorizationRequest
from govbr_auth.core.errors import (
    GovBrAuthError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import TransactionStore

_OAUTH_REJECTION_MESSAGE = "Gov.br rejected the authorization code"
_PROVIDER_FAILURE_MESSAGE = "Gov.br provider request failed"
_PROVIDER_TIMEOUT_MESSAGE = "Gov.br provider request timed out"
_TOKEN_RESPONSE_MESSAGE = "Gov.br token response is invalid"
_JWKS_REJECTION_MESSAGE = "Gov.br rejected the JWKS request"
_JWKS_RESPONSE_MESSAGE = "Gov.br JWKS response is invalid"
_USERINFO_REJECTION_MESSAGE = "Gov.br rejected the access token"
_USERINFO_RESPONSE_MESSAGE = "Gov.br userinfo response is invalid"


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """Return validated tokens and a shallowly immutable ID-claim mapping.

    The top-level mapping cannot be changed. Nested values retain the mutability
    provided by the token decoder.
    """

    tokens: TokenSet
    id_token_claims: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id_token_claims",
            MappingProxyType(dict(self.id_token_claims)),
        )


class GovBrClient:
    """Coordinate authorization, token exchange, validation, and userinfo I/O."""

    def __init__(
        self,
        settings: GovBrSettings,
        transactions: TransactionStore,
        validator: IdTokenValidator,
        http: httpx.AsyncClient,
    ) -> None:
        """Store validated configuration and injected collaborators."""
        self._settings = settings
        self._transactions = transactions
        self._validator = validator
        self._http = http
        self._authorization = AuthorizationBuilder(settings, transactions)
        self._timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.read_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        )

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        """Create an authorization request bound to a stored transaction."""
        return self._authorization.build(now=now)

    async def exchange_code(
        self,
        *,
        code: str,
        state: str,
        now: datetime,
    ) -> AuthenticationResult:
        """Exchange a one-time authorization transaction for validated tokens."""
        transaction = self._transactions.consume(state, now=now)
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": str(self._settings.redirect_uri),
            "code_verifier": transaction.code_verifier.get_secret_value(),
        }
        response = await self._post_token(form)
        if response.status_code in {
            httpx.codes.BAD_REQUEST,
            httpx.codes.UNAUTHORIZED,
            httpx.codes.FORBIDDEN,
        }:
            self._raise_http_error(
                ProviderRejectedError,
                _OAUTH_REJECTION_MESSAGE,
                response.status_code,
            )
        if response.is_error:
            self._raise_http_error(
                ProviderUnavailableError,
                _PROVIDER_FAILURE_MESSAGE,
                response.status_code,
            )

        tokens = self._parse_tokens(response)
        jwks_response = await self._get_jwks()
        if jwks_response.status_code in {
            httpx.codes.BAD_REQUEST,
            httpx.codes.UNAUTHORIZED,
            httpx.codes.FORBIDDEN,
        }:
            self._raise_http_error(
                ProviderRejectedError,
                _JWKS_REJECTION_MESSAGE,
                jwks_response.status_code,
            )
        if not jwks_response.is_success:
            self._raise_http_error(
                ProviderUnavailableError,
                _PROVIDER_FAILURE_MESSAGE,
                jwks_response.status_code,
            )

        jwks = self._parse_jwks(jwks_response)
        claims = self._validator.validate(
            tokens.id_token,
            transaction.nonce,
            jwks=jwks,
            now=now,
        )
        return AuthenticationResult(tokens=tokens, id_token_claims=claims)

    async def userinfo(
        self,
        access_token: SecretStr,
        *,
        expected_subject: str,
    ) -> GovBrUser:
        """Fetch user information bound to the validated ID-token subject."""
        response = await self._get_userinfo(access_token)
        if response.status_code in {
            httpx.codes.BAD_REQUEST,
            httpx.codes.UNAUTHORIZED,
            httpx.codes.FORBIDDEN,
        }:
            self._raise_http_error(
                ProviderRejectedError,
                _USERINFO_REJECTION_MESSAGE,
                response.status_code,
            )
        if response.is_error:
            self._raise_http_error(
                ProviderUnavailableError,
                _PROVIDER_FAILURE_MESSAGE,
                response.status_code,
            )

        user = self._parse_userinfo(response)
        if user.sub != expected_subject:
            self._raise_invalid_response(
                _USERINFO_RESPONSE_MESSAGE,
                "SubjectMismatch",
            )
        return user

    async def _post_token(self, form: Mapping[str, str]) -> httpx.Response:
        try:
            return await self._http.post(
                str(self._settings.token_url),
                data=form,
                auth=(
                    self._settings.client_id,
                    self._settings.client_secret.get_secret_value(),
                ),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            failure_message = _PROVIDER_TIMEOUT_MESSAGE
            failure_type = type(error).__name__
        except httpx.TransportError as error:
            failure_message = _PROVIDER_FAILURE_MESSAGE
            failure_type = type(error).__name__

        self._raise_transport_error(
            ProviderUnavailableError,
            failure_message,
            failure_type,
        )

    async def _get_userinfo(self, access_token: SecretStr) -> httpx.Response:
        try:
            return await self._http.get(
                str(self._settings.userinfo_url),
                headers={"Authorization": f"Bearer {access_token.get_secret_value()}"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            failure_message = _PROVIDER_TIMEOUT_MESSAGE
            failure_type = type(error).__name__
        except httpx.TransportError as error:
            failure_message = _PROVIDER_FAILURE_MESSAGE
            failure_type = type(error).__name__

        self._raise_transport_error(
            ProviderUnavailableError,
            failure_message,
            failure_type,
        )

    async def _get_jwks(self) -> httpx.Response:
        try:
            return await self._http.get(
                str(self._settings.jwks_url),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            failure_message = _PROVIDER_TIMEOUT_MESSAGE
            failure_type = type(error).__name__
        except httpx.TransportError as error:
            failure_message = _PROVIDER_FAILURE_MESSAGE
            failure_type = type(error).__name__

        self._raise_transport_error(
            ProviderUnavailableError,
            failure_message,
            failure_type,
        )

    @staticmethod
    def _parse_tokens(response: httpx.Response) -> TokenSet:
        try:
            payload = response.json()
            return TokenSet.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as error:
            failure_type = type(error).__name__

        GovBrClient._raise_invalid_response(_TOKEN_RESPONSE_MESSAGE, failure_type)

    @staticmethod
    def _parse_userinfo(response: httpx.Response) -> GovBrUser:
        try:
            payload = response.json()
            return GovBrUser.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as error:
            failure_type = type(error).__name__

        GovBrClient._raise_invalid_response(_USERINFO_RESPONSE_MESSAGE, failure_type)

    @staticmethod
    def _parse_jwks(response: httpx.Response) -> Mapping[str, object]:
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

        GovBrClient._raise_invalid_response(_JWKS_RESPONSE_MESSAGE, failure_type)

    @staticmethod
    def _raise_transport_error(
        error_type: type[GovBrAuthError],
        message: str,
        failure_type: str,
    ) -> NoReturn:
        safe_cause = RuntimeError(f"Gov.br HTTP transport failed ({failure_type})")
        raise error_type(message) from safe_cause

    @staticmethod
    def _raise_http_error(
        error_type: type[GovBrAuthError],
        message: str,
        status_code: int,
    ) -> NoReturn:
        safe_cause = RuntimeError(f"Gov.br provider returned HTTP status {status_code}")
        raise error_type(message) from safe_cause

    @staticmethod
    def _raise_invalid_response(message: str, failure_type: str) -> NoReturn:
        safe_cause = ValueError(f"Gov.br response validation failed ({failure_type})")
        raise GovBrAuthError(message) from safe_cause
