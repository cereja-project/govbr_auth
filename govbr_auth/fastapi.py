"""Thin asynchronous FastAPI adapter for the strict Gov.br OAuth core."""

from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING

import httpx
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
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
    _fake_callback_url,
    create_govbr_runtime,
)

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeGovBrRuntime, FakeUserRepository

__all__ = [
    "AuthContext",
    "AuthErrorHandler",
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
AuthErrorHandler = Callable[[GovBrAuthError], Awaitable[Response]]


def create_govbr_router(
    *,
    client: GovBrClient,
    on_success: AuthSuccessHandler,
    on_error: AuthErrorHandler | None = None,
    expose_tokens: bool = False,
    prefix: str = "/auth/govbr",
    clock: Callable[[], datetime] = utc_now,
) -> APIRouter:
    """Create consumer authentication routes backed by a strict core client."""
    prefix = _validate_router_prefix(prefix)
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
            if on_error is not None:
                return await on_error(error)
            return _auth_error_response(error)

        context = AuthContext(
            user=user,
            claims=result.id_token_claims,
            tokens=result.tokens if expose_tokens else None,
        )
        return await on_success(context)

    return router


class GovBrAuth:
    """Expose runtime-backed Gov.br routes as an idiomatic FastAPI router."""

    def __init__(
        self,
        *,
        on_success: AuthSuccessHandler,
        settings: GovBrRuntimeSettings | None = None,
        runtime: GovBrRuntime | None = None,
        on_error: AuthErrorHandler | None = None,
        expose_tokens: bool = False,
        prefix: str = "/auth/govbr",
        clock: Callable[[], datetime] = utc_now,
        user_repository: "FakeUserRepository | None" = None,
    ) -> None:
        if settings is not None and runtime is not None:
            raise TypeError("settings and runtime are mutually exclusive")
        prefix = _validate_router_prefix(prefix)
        if runtime is None:
            resolved_settings = _settings_for_router_callback(
                settings or GovBrRuntimeSettings.from_environment(),
                prefix,
            )
            runtime = create_govbr_runtime(
                resolved_settings,
                fake_transport_factory=lambda fake: _fake_asgi_transport(
                    fake,
                    clock=clock,
                ),
                clock=clock,
                user_repository=user_repository,
            )
        else:
            _validate_runtime_callback(runtime, prefix)
        self._runtime = runtime

        @asynccontextmanager
        async def lifespan(_: object):
            async with runtime:
                yield

        router = APIRouter(lifespan=lifespan)
        router.include_router(
            create_govbr_router(
                client=runtime.client,
                on_success=on_success,
                on_error=on_error,
                expose_tokens=expose_tokens,
                prefix=prefix,
                clock=clock,
            )
        )
        if runtime.fake is not None:
            from govbr_auth.fake.fastapi import create_fake_govbr_router

            router.include_router(create_fake_govbr_router(runtime.fake, clock=clock))
        self._router = router

    @property
    def router(self) -> APIRouter:
        """Return the framework-native router for explicit application inclusion."""
        return self._router

    @property
    def runtime(self) -> GovBrRuntime:
        """Return the neutral runtime consumed by this adapter."""
        return self._runtime


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


def _validate_router_prefix(prefix: str) -> str:
    if prefix and not prefix.startswith("/"):
        raise ValueError("prefix must be empty or start with '/'")
    if prefix.endswith("/"):
        raise ValueError("prefix must not end with '/'")
    return prefix


def _settings_for_router_callback(
    settings: GovBrRuntimeSettings,
    prefix: str,
) -> GovBrRuntimeSettings:
    if settings.provider is not GovBrProvider.FAKE:
        return settings
    expected = _fake_callback_url(settings.fake_host, settings.fake_port, prefix)
    configured = (
        None if settings.fake_redirect_uri is None else str(settings.fake_redirect_uri)
    )
    default = _fake_callback_url(
        settings.fake_host,
        settings.fake_port,
        "/auth/govbr",
    )
    if configured is not None and configured not in {default, expected}:
        raise ValueError("fake redirect URI does not match the router callback")
    values = settings.model_dump()
    values["fake_redirect_uri"] = expected
    return GovBrRuntimeSettings.model_validate(values)


def _validate_runtime_callback(runtime: GovBrRuntime, prefix: str) -> None:
    if runtime.fake is None:
        return
    expected = _fake_callback_url(
        runtime.settings.fake_host,
        runtime.settings.fake_port,
        prefix,
    )
    configured = str(runtime.fake.settings.clients[0].registered_redirect_uris[0])
    if configured != expected:
        raise ValueError("fake runtime redirect URI does not match the router callback")


def _fake_asgi_transport(
    runtime: "FakeGovBrRuntime",
    *,
    clock: Callable[[], datetime],
) -> httpx.AsyncBaseTransport:
    """Create the FastAPI-owned in-process transport for a fake runtime."""
    from govbr_auth.fake.fastapi import create_fake_govbr_router

    provider_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    provider_app.include_router(create_fake_govbr_router(runtime, clock=clock))
    return httpx.ASGITransport(
        app=provider_app,
    )
