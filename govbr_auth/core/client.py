"""Asynchronous HTTP orchestration for the strict Gov.br OAuth core."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import NoReturn

import httpx
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationBuilder, AuthorizationRequest
from govbr_auth.core.errors import (
    GovBrAuthError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from govbr_auth.core.decoders import decode_jwks, decode_tokens, decode_userinfo
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import TransactionCodec
from govbr_auth.core.transport import GovBrHttpTransport

_OAUTH_REJECTION_MESSAGE = "Gov.br rejected the authorization code"
_PROVIDER_FAILURE_MESSAGE = "Gov.br provider request failed"
_JWKS_REJECTION_MESSAGE = "Gov.br rejected the JWKS request"
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
        transactions: TransactionCodec,
        validator: IdTokenValidator,
        http: httpx.AsyncClient,
    ) -> None:
        """Store validated configuration and injected collaborators."""
        self._settings = settings
        self._transactions = transactions
        self._validator = validator
        self._http = http
        self._transport = GovBrHttpTransport(settings, http)
        self._authorization = AuthorizationBuilder(settings, transactions)

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        """Create an authorization request bound to a protected transaction."""
        return self._authorization.build(now=now)

    def validate_state(self, state: str, *, now: datetime) -> None:
        """Validate a callback state without exchanging an authorization code."""
        self._transactions.decode(state, now=now)

    def logout_url(self) -> str:
        """Build the configured provider logout URL."""
        return self._authorization.build_logout()

    async def exchange_code(
        self,
        *,
        code: str,
        state: str,
        now: datetime,
    ) -> AuthenticationResult:
        """Exchange a one-time authorization transaction for validated tokens."""
        transaction = self._transactions.decode(state, now=now)
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
        return await self._transport.post_token(form)

    async def _get_userinfo(self, access_token: SecretStr) -> httpx.Response:
        return await self._transport.get_userinfo(access_token)

    async def _get_jwks(self) -> httpx.Response:
        return await self._transport.get_jwks()

    @staticmethod
    def _parse_tokens(response: httpx.Response) -> TokenSet:
        return decode_tokens(response)

    @staticmethod
    def _parse_userinfo(response: httpx.Response) -> GovBrUser:
        return decode_userinfo(response)

    @staticmethod
    def _parse_jwks(response: httpx.Response) -> Mapping[str, object]:
        return decode_jwks(response)

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
