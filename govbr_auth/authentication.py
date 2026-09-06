"""Framework-neutral authentication application service."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn, Protocol

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.errors import InvalidIdTokenError, ProviderRejectedError
from govbr_auth.core.models import GovBrUser, TokenSet

if TYPE_CHECKING:
    from govbr_auth.core.client import AuthenticationResult


class AuthenticationClient(Protocol):
    """Describe the core client operations needed by the auth use case."""

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest: ...

    def validate_state(self, state: str, *, now: datetime) -> None: ...

    def logout_url(self) -> str: ...

    async def exchange_code(
        self, *, code: str, state: str, now: datetime
    ) -> "AuthenticationResult": ...

    async def userinfo(
        self, access_token: object, *, expected_subject: str
    ) -> GovBrUser: ...


@dataclass(frozen=True, slots=True)
class AuthenticationContext:
    """Expose validated user data without binding it to a web framework."""

    user: GovBrUser
    claims: Mapping[str, object]
    tokens: TokenSet | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "claims", MappingProxyType(dict(self.claims)))


class AuthenticationService:
    """Coordinate the framework-independent consumer authentication flow."""

    def __init__(
        self,
        client: AuthenticationClient,
        *,
        expose_tokens: bool = False,
    ) -> None:
        self._client = client
        self._expose_tokens = expose_tokens

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        """Create an authorization request through the core client."""
        return self._client.authorization_url(now=now)

    def logout_url(self) -> str:
        """Return the fixed provider logout URL configured for the client."""
        return self._client.logout_url()

    def provider_error(
        self,
        *,
        error: str,
        state: str,
        error_description: str | None,
        now: datetime,
    ) -> NoReturn:
        """Validate an OAuth error callback and raise a safe public failure."""
        del error, error_description
        self._client.validate_state(state, now=now)
        raise ProviderRejectedError("Gov.br rejected the authorization request")

    async def authenticate(
        self,
        *,
        code: str,
        state: str,
        now: datetime,
    ) -> AuthenticationContext:
        """Exchange, validate, and resolve the user for an OAuth callback."""
        result = await self._client.exchange_code(code=code, state=state, now=now)
        expected_subject = result.id_token_claims.get("sub")
        if not isinstance(expected_subject, str) or not expected_subject.strip():
            raise InvalidIdTokenError("Validated ID token has no usable subject")

        user = await self._client.userinfo(
            result.tokens.access_token,
            expected_subject=expected_subject,
        )
        return AuthenticationContext(
            user=user,
            claims=result.id_token_claims,
            tokens=result.tokens if self._expose_tokens else None,
        )
