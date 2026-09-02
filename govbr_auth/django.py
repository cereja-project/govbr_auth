"""Native synchronous Django adapter for the Gov.br authentication engine."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.http import HttpRequest, HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import URLPattern, path
from django.views.decorators.csrf import csrf_exempt

from govbr_auth.adapters._errors import (
    INVALID_CALLBACK_MESSAGE,
    describe_auth_error,
)
from govbr_auth.adapters._runtime import adapter_callback_path, create_adapter_runtime
from govbr_auth.adapters._sync import run_sync
from govbr_auth.authentication import AuthenticationContext, AuthenticationService
from govbr_auth.core.errors import GovBrAuthError
from govbr_auth.fake.django import create_fake_govbr_urlpatterns
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.presentation import DEMO_PAGE_PATH, render_demo_page
from govbr_auth.runtime import GovBrApplicationSettings, GovBrRuntime
from govbr_auth.runtime_settings import _is_canonical_path_prefix

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeUserRepository


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


AuthSuccessHandler = Callable[[AuthenticationContext, HttpRequest], HttpResponse]
AuthErrorHandler = Callable[[GovBrAuthError, HttpRequest], HttpResponse]


class GovBrAuth:
    """Expose Gov.br consumer and conditional FakeGov Django URL patterns."""

    def __init__(
        self,
        *,
        on_success: AuthSuccessHandler,
        settings: GovBrApplicationSettings | None = None,
        runtime: GovBrRuntime | None = None,
        demo_page: bool = False,
        on_error: AuthErrorHandler | None = None,
        expose_tokens: bool = False,
        prefix: str = "/auth/govbr",
        clock: Callable[[], datetime] = utc_now,
        user_repository: "FakeUserRepository | None" = None,
    ) -> None:
        if not _is_canonical_path_prefix(prefix, allow_empty=True):
            raise ValueError("prefix must be an empty string or a canonical path")
        self._prefix = prefix.lstrip("/")
        self._login_path = f"{prefix}/login" if prefix else "/login"
        self._clock = clock
        self._on_success = on_success
        self._on_error = on_error
        self._owner, self._demo_page_enabled = create_adapter_runtime(
            settings=settings,
            runtime=runtime,
            demo_page=demo_page,
            prefix=prefix,
            clock=clock,
            user_repository=user_repository,
            fake_transport_factory=lambda fake: FakeGovHttpTransport(
                fake,
                clock=clock,
            ),
        )
        self._service = AuthenticationService(
            self._owner.runtime.client,
            expose_tokens=expose_tokens,
        )
        self._urlpatterns = self._build_urlpatterns()

    @property
    def urlpatterns(self) -> list[URLPattern]:
        """Return URL patterns for explicit inclusion in the project."""
        return self._urlpatterns

    def close(self) -> None:
        """Close an adapter-owned runtime without closing a borrowed runtime."""
        self._owner.close()

    def _build_urlpatterns(self) -> list[URLPattern]:
        prefix = f"{self._prefix}/" if self._prefix else ""
        callback_path = adapter_callback_path(
            self._owner.runtime,
            f"/{self._prefix}" if self._prefix else "",
        ).lstrip("/")
        patterns = [
            path(f"{prefix}login", self._login, name="govbr-auth-login"),
            path(
                callback_path,
                self._callback,
                name="govbr-auth-callback",
            ),
        ]
        if self._demo_page_enabled:
            patterns.append(
                path(
                    DEMO_PAGE_PATH.lstrip("/"),
                    self._demo_page,
                    name="govbr-auth-demo",
                )
            )
        fake_runtime = self._owner.runtime.fake
        if fake_runtime is not None:
            patterns.extend(
                create_fake_govbr_urlpatterns(
                    fake_runtime,
                    application=fake_runtime.http_application,
                    clock=self._clock,
                )
            )
        return patterns

    def _demo_page(self, request: HttpRequest) -> HttpResponse:
        del request
        return HttpResponse(
            render_demo_page(
                provider=self._owner.runtime.provider,
                login_path=self._login_path,
            ),
            content_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    def _login(self, request: HttpRequest) -> HttpResponseRedirect:
        authorization = self._service.authorization_url(now=self._clock())
        return HttpResponseRedirect(authorization.url)

    @csrf_exempt
    def _callback(self, request: HttpRequest) -> HttpResponse:
        code = request.POST.get("code") or request.GET.get("code")
        state = request.POST.get("state") or request.GET.get("state")
        if (
            not isinstance(code, str)
            or not code.strip()
            or not isinstance(state, str)
            or not state.strip()
        ):
            return JsonResponse(
                {"error": "invalid_callback", "message": INVALID_CALLBACK_MESSAGE},
                status=400,
            )
        try:

            async def authenticate():
                return await self._service.authenticate(
                    code=code,
                    state=state,
                    now=self._clock(),
                )

            context = run_sync(authenticate)
        except GovBrAuthError as error:
            if self._on_error is not None:
                return self._on_error(error, request)
            return _auth_error_response(error)
        return self._on_success(context, request)


def _auth_error_response(error: GovBrAuthError) -> JsonResponse:
    description = describe_auth_error(error)
    return JsonResponse(
        {"error": error.code, "message": description.message},
        status=description.status_code,
    )
