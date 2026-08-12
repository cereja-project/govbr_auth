"""Thin asynchronous FastAPI adapter for the strict Gov.br OAuth core."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse, RedirectResponse, Response

from govbr_auth.core.client import GovBrClient
from govbr_auth.core.errors import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidIdTokenError,
    InvalidStateError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from govbr_auth.core.models import GovBrUser, TokenSet

__all__ = [
    "AuthContext",
    "AuthSuccessHandler",
    "GovBrAuth",
    "create_govbr_router",
]


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time for core operations."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Expose validated user data to a consumer success handler."""

    user: GovBrUser
    claims: Mapping[str, object]
    tokens: TokenSet | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "claims", MappingProxyType(dict(self.claims)))


AuthSuccessHandler = Callable[[AuthContext], Awaitable[Response]]


def create_govbr_router(
    *,
    client: GovBrClient,
    on_success: AuthSuccessHandler,
    expose_tokens: bool = False,
    prefix: str = "/auth/govbr",
    clock: Callable[[], datetime] = utc_now,
) -> APIRouter:
    """Create consumer authentication routes backed by a strict core client."""
    router = APIRouter(prefix=prefix)

    @router.get("/login")
    async def login() -> RedirectResponse:
        authorization = client.authorization_url(now=clock())
        return RedirectResponse(authorization.url, status_code=302)

    @router.get("/callback")
    async def callback(code: str, state: str) -> Response:
        try:
            result = await client.exchange_code(code=code, state=state, now=clock())
            expected_subject = result.id_token_claims.get("sub")
            if not isinstance(expected_subject, str) or not expected_subject.strip():
                raise InvalidIdTokenError("Validated ID token has no usable subject")
            user = await client.userinfo(
                result.tokens.access_token,
                expected_subject=expected_subject,
            )
        except GovBrAuthError as error:
            return _auth_error_response(error)

        context = AuthContext(
            user=user,
            claims=result.id_token_claims,
            tokens=result.tokens if expose_tokens else None,
        )
        return await on_success(context)

    return router


class GovBrAuth:
    """Provide explicit installation of the Gov.br routes on a FastAPI app."""

    def __init__(
        self,
        *,
        client: GovBrClient,
        on_success: AuthSuccessHandler,
        expose_tokens: bool = False,
        prefix: str = "/auth/govbr",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.router = create_govbr_router(
            client=client,
            on_success=on_success,
            expose_tokens=expose_tokens,
            prefix=prefix,
            clock=clock,
        )

    def install(self, app: FastAPI) -> None:
        """Install only the consumer-facing authentication routes."""
        app.include_router(self.router)


def _auth_error_response(error: GovBrAuthError) -> JSONResponse:
    if isinstance(error, (InvalidStateError, ExpiredTransactionError)):
        status_code = 400
        safe_message = "The authorization request is invalid or expired."
    elif isinstance(error, ProviderRejectedError):
        status_code = 502
        safe_message = "Gov.br rejected the request."
    elif isinstance(error, ProviderUnavailableError):
        status_code = 503
        safe_message = "Gov.br is temporarily unavailable."
    else:
        status_code = 502
        safe_message = "Gov.br authentication failed."
    return JSONResponse(
        status_code=status_code,
        content={"error": error.code, "message": safe_message},
    )
