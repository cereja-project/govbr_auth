"""Native synchronous Flask adapter for the Gov.br authentication engine."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flask import Blueprint, Flask, jsonify, redirect, request

from govbr_auth.adapters._errors import (
    INVALID_CALLBACK_MESSAGE,
    describe_auth_error,
)
from govbr_auth.adapters._runtime import adapter_callback_path, create_adapter_runtime
from govbr_auth.adapters._sync import run_sync
from govbr_auth.authentication import AuthenticationContext, AuthenticationService
from govbr_auth.core.errors import GovBrAuthError
from govbr_auth.fake.flask import create_fake_govbr_blueprint
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.runtime import GovBrRuntime, GovBrRuntimeSettings
from govbr_auth.runtime_settings import _is_canonical_path_prefix

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeUserRepository


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


AuthSuccessHandler = Callable[[AuthenticationContext, object], object]
AuthErrorHandler = Callable[[GovBrAuthError, object], object]


class GovBrAuth:
    """Expose Gov.br consumer and conditional FakeGov Flask blueprints."""

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
        self._blueprint = self._build_blueprint(prefix)
        fake_runtime = self._owner.runtime.fake
        self._fake_blueprint = (
            create_fake_govbr_blueprint(
                fake_runtime,
                application=fake_runtime.http_application,
                clock=self._clock,
            )
            if fake_runtime is not None
            else None
        )

    @property
    def blueprint(self) -> Blueprint:
        """Return the consumer blueprint for explicit app registration."""
        return self._blueprint

    def close(self) -> None:
        """Close an adapter-owned runtime without closing a borrowed runtime."""
        self._owner.close()

    def register(self, application: Flask) -> None:
        """Register consumer and conditional FakeGov routes on a Flask app."""
        application.register_blueprint(self._blueprint)
        if self._fake_blueprint is not None:
            application.register_blueprint(self._fake_blueprint)

    def _build_blueprint(self, prefix: str) -> Blueprint:
        blueprint = Blueprint("govbr_auth", __name__)
        login_path = f"{prefix}/login" if prefix else "/login"
        callback_path = adapter_callback_path(self._owner.runtime, prefix)

        @blueprint.get(login_path)
        def login():
            authorization = self._service.authorization_url(now=self._clock())
            return redirect(authorization.url)

        @blueprint.route(callback_path, methods=["GET", "POST"])
        def callback():
            code = request.values.get("code")
            state = request.values.get("state")
            if (
                not isinstance(code, str)
                or not code.strip()
                or not isinstance(state, str)
                or not state.strip()
            ):
                return (
                    jsonify(
                        {
                            "error": "invalid_callback",
                            "message": INVALID_CALLBACK_MESSAGE,
                        }
                    ),
                    400,
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

        return blueprint


def _auth_error_response(error: GovBrAuthError):
    description = describe_auth_error(error)
    return (
        jsonify({"error": error.code, "message": description.message}),
        description.status_code,
    )
