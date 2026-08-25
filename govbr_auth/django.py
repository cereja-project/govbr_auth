"""Native synchronous Django adapter for the Gov.br authentication engine."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.http import HttpRequest, HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import URLPattern, path
from django.views.decorators.csrf import csrf_exempt

from govbr_auth.adapters._runtime import create_adapter_runtime
from govbr_auth.adapters._sync import run_sync
from govbr_auth.authentication import AuthenticationContext, AuthenticationService
from govbr_auth.core.errors import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidStateError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from govbr_auth.fake.django import create_fake_govbr_urlpatterns
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.runtime import GovBrProvider, GovBrRuntime, GovBrRuntimeSettings
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
        settings: GovBrRuntimeSettings | None = None,
        runtime: GovBrRuntime | None = None,
        on_error: AuthErrorHandler | None = None,
        expose_tokens: bool = False,
        prefix: str = "/auth/govbr",
        clock: Callable[[], datetime] = utc_now,
        user_repository: "FakeUserRepository | None" = None,
    ) -> None:
        if not _is_canonical_path_prefix(prefix, allow_empty=True):
            raise ValueError("prefix must be an empty string or a canonical path")
        self._prefix = prefix.lstrip("/")
        self._clock = clock
        self._on_success = on_success
        self._on_error = on_error
        self._owner = create_adapter_runtime(
            settings=settings,
            runtime=runtime,
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
        patterns = [
            path(f"{prefix}login", self._login, name="govbr-auth-login"),
            path(
                f"{prefix}callback",
                self._callback,
                name="govbr-auth-callback",
            ),
        ]
        if self._owner.runtime.fake is not None:
            patterns.extend(
                create_fake_govbr_urlpatterns(
                    self._owner.runtime.fake,
                    clock=self._clock,
                )
            )
        return patterns

    def _login(self, request: HttpRequest) -> HttpResponseRedirect:
        authorization = self._service.authorization_url(now=self._clock())
        return HttpResponseRedirect(authorization.url)

    @csrf_exempt
    def _callback(self, request: HttpRequest) -> HttpResponse:
        code = request.POST.get("code") or request.GET.get("code")
        state = request.POST.get("state") or request.GET.get("state")
        if not isinstance(code, str) or not code.strip() or not isinstance(state, str) or not state.strip():
            return JsonResponse(
                {"error": "invalid_callback", "message": "Callback parameters are invalid."},
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
    if isinstance(error, (InvalidStateError, ExpiredTransactionError)):
        status_code = 400
        message = "The authorization request is invalid or expired."
    elif isinstance(error, ProviderRejectedError):
        status_code = 502
        message = "Gov.br rejected the request."
    elif isinstance(error, ProviderUnavailableError):
        status_code = 503
        message = "Gov.br is temporarily unavailable."
    else:
        status_code = 502
        message = "Gov.br authentication failed."
    return JsonResponse(
        {"error": error.code, "message": message},
        status=status_code,
    )
