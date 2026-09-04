"""Thin asynchronous FastAPI adapter for the strict Gov.br OAuth core."""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from govbr_auth.adapters._errors import describe_auth_error
from govbr_auth.adapters._application import create_adapter_application
from govbr_auth.authentication import AuthenticationContext, AuthenticationService
from govbr_auth.core.client import GovBrClient
from govbr_auth.core.errors import GovBrAuthError
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.presentation import DEMO_PAGE_PATH, render_demo_page
from govbr_auth.runtime import GovBrRuntime, GovBrRuntimeSettings
from govbr_auth.runtime_settings import _is_canonical_path_prefix

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeUserRepository

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


AuthContext = AuthenticationContext
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
    service = AuthenticationService(client, expose_tokens=expose_tokens)
    return _create_govbr_router(
        service=service,
        on_success=on_success,
        on_error=on_error,
        router_prefix=prefix,
        login_path="/login",
        callback_path="/callback",
        clock=clock,
    )


def _create_govbr_router(
    *,
    service: AuthenticationService,
    on_success: AuthSuccessHandler,
    on_error: AuthErrorHandler | None,
    router_prefix: str,
    login_path: str,
    callback_path: str,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix=router_prefix)

    @router.get(login_path)
    async def login() -> RedirectResponse:
        authorization = service.authorization_url(now=clock())
        return RedirectResponse(authorization.url, status_code=302)

    @router.get(callback_path)
    async def callback(code: str, state: str) -> Response:
        try:
            context = await service.authenticate(
                code=code,
                state=state,
                now=clock(),
            )
        except GovBrAuthError as error:
            if on_error is not None:
                return await on_error(error)
            return _auth_error_response(error)

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
        application = create_adapter_application(
            settings=settings,
            runtime=runtime,
            prefix=prefix,
            expose_tokens=expose_tokens,
            clock=clock,
            user_repository=user_repository,
            fake_transport_factory=lambda fake: FakeGovHttpTransport(
                fake,
                clock=clock,
            ),
        )
        self._application = application
        self._runtime = application.runtime

        @asynccontextmanager
        async def lifespan(_: object):
            try:
                yield
            finally:
                await application.aclose()

        router = APIRouter(lifespan=lifespan)
        router.include_router(
            _create_govbr_router(
                service=application.service,
                on_success=on_success,
                on_error=on_error,
                router_prefix="",
                login_path=application.login_path,
                callback_path=application.callback_path,
                clock=clock,
            )
        )
        if self._runtime.fake is not None:
            from govbr_auth.fake.fastapi import create_fake_govbr_router

            @router.get("/", include_in_schema=False)
            @router.get(DEMO_PAGE_PATH, include_in_schema=False)
            async def demo_page() -> HTMLResponse:
                return HTMLResponse(
                    render_demo_page(
                        provider=self._runtime.provider,
                        login_path=f"{prefix}/login" if prefix else "/login",
                    ),
                    headers={"Cache-Control": "no-store"},
                )

            router.include_router(
                create_fake_govbr_router(
                    self._runtime.fake,
                    application=self._runtime.fake.http_application,
                    clock=clock,
                )
            )
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
    description = describe_auth_error(error)
    return JSONResponse(
        status_code=description.status_code,
        content={"error": error.code, "message": description.message},
    )


def _validate_router_prefix(prefix: str) -> str:
    if prefix and not prefix.startswith("/"):
        raise ValueError("prefix must be empty or start with '/'")
    if prefix.endswith("/"):
        raise ValueError("prefix must not end with '/'")
    if not _is_canonical_path_prefix(prefix, allow_empty=True):
        raise ValueError("prefix must be an empty string or a canonical path")
    return prefix
