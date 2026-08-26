"""Explicit FastAPI and ASGI factories for the local Fake Gov.br provider."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx
from fastapi import APIRouter, FastAPI

from govbr_auth.fake.http.routes import build_fake_govbr_routes
from govbr_auth.fake.http.application import (
    FakeGovHttpApplication,
    resolve_fake_http_application,
)
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.fake.credentials import FakeCredentialAuthenticator
from govbr_auth.fake.provider import FakeGovBrProvider
from govbr_auth.fake.runtime import (
    FakeGovSimulator,
    FakeUserRepository,
    create_fake_gov_simulator,
)
from govbr_auth.fastapi import utc_now
from govbr_auth.fake.launcher import create_end_to_end_app
from govbr_auth.presentation import render_error, render_home, render_success
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntimeSettings,
    create_govbr_runtime,
)


class _FakeHttpRuntime(Protocol):
    """Expose only the canonical runtime fields required by HTTP routes."""

    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator | None
    prefix: str


@dataclass(frozen=True, slots=True)
class _ProviderRuntimeAdapter:
    """Adapt an advanced supplied provider without composing new resources."""

    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator | None
    prefix: str


def create_fake_govbr_router(
    runtime: FakeGovSimulator | FakeGovBrProvider,
    *,
    prefix: str | None = None,
    application: FakeGovHttpApplication | None = None,
    credential_authenticator: FakeCredentialAuthenticator | None = None,
    automatic_subject: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> APIRouter:
    """Create explicitly mounted fake-provider routes below ``prefix``."""
    runtime = _as_http_runtime(
        runtime,
        prefix=prefix,
        credential_authenticator=credential_authenticator,
    )
    application = _resolve_http_application(
        runtime,
        application=application,
        clock=clock,
    )
    return build_fake_govbr_routes(
        runtime,
        automatic_subject=automatic_subject,
        clock=clock,
        application=application,
    )


def create_fake_govbr_app(
    runtime: FakeGovSimulator | FakeGovBrProvider,
    *,
    application: FakeGovHttpApplication | None = None,
    credential_authenticator: FakeCredentialAuthenticator | None = None,
    automatic_subject: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Create a standalone ASGI fake provider with routes at the application root."""
    fastapi_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    runtime = _as_http_runtime(
        runtime,
        prefix=None if isinstance(runtime, FakeGovSimulator) else "",
        credential_authenticator=credential_authenticator,
    )
    http_application = _resolve_http_application(
        runtime,
        application=application,
        clock=clock,
    )
    fastapi_app.include_router(
        build_fake_govbr_routes(
            runtime,
            automatic_subject=automatic_subject,
            clock=clock,
            application=http_application,
        )
    )
    return fastapi_app


def create_fake_app(
    settings: GovBrRuntimeSettings | None = None,
    *,
    clock: Callable[[], datetime] = utc_now,
    user_repository: FakeUserRepository | None = None,
) -> FastAPI:
    """Create the provider-only or complete local fake application profile."""
    resolved_settings = settings or _launcher_settings()
    if resolved_settings.provider is not GovBrProvider.FAKE:
        raise ValueError("fake launcher requires the fake provider")
    if not resolved_settings.fake_end_to_end:
        runtime = create_fake_gov_simulator(
            resolved_settings,
            clock=clock,
            user_repository=user_repository,
        )
        return create_fake_govbr_app(
            runtime,
            application=runtime.http_application,
            clock=clock,
        )

    runtime = create_govbr_runtime(
        resolved_settings,
        fake_transport_factory=lambda fake: _fake_asgi_transport(fake, clock=clock),
        clock=clock,
        user_repository=user_repository,
    )
    return create_end_to_end_app(
        runtime,
        clock=clock,
        render_success_page=render_success,
        render_error_page=render_error,
        render_home_page=render_home,
    )


def run() -> None:
    """Run the selected fake profile on its validated loopback endpoint."""
    import uvicorn

    settings = _launcher_settings()
    uvicorn.run(
        "govbr_auth.fake:create_fake_app",
        factory=True,
        host=settings.fake_host,
        port=settings.fake_port,
    )


def _fake_asgi_transport(
    runtime: FakeGovSimulator,
    *,
    clock: Callable[[], datetime],
) -> httpx.AsyncBaseTransport:
    """Serve provider calls through the simulator-owned neutral facade."""
    return FakeGovHttpTransport(runtime, clock=clock)


def _launcher_settings() -> GovBrRuntimeSettings:
    """Default this explicit fake entry point without changing library defaults."""
    environ = dict(os.environ)
    environ.setdefault("GOVBR_PROVIDER", GovBrProvider.FAKE.value)
    return GovBrRuntimeSettings.from_environment(environ)


def _as_http_runtime(
    runtime: FakeGovSimulator | FakeGovBrProvider,
    *,
    prefix: str | None,
    credential_authenticator: FakeCredentialAuthenticator | None,
) -> _FakeHttpRuntime:
    if isinstance(runtime, FakeGovSimulator):
        if prefix is not None and prefix != runtime.prefix:
            raise ValueError("prefix does not match runtime prefix")

        if credential_authenticator is None:
            return runtime
        return _ProviderRuntimeAdapter(
            provider=runtime.provider,
            credential_authenticator=credential_authenticator,
            prefix=runtime.prefix,
        )
    return _ProviderRuntimeAdapter(
        provider=runtime,
        credential_authenticator=credential_authenticator,
        prefix="/fake-govbr" if prefix is None else prefix,
    )


def _resolve_http_application(
    runtime: _FakeHttpRuntime,
    *,
    application: FakeGovHttpApplication | None,
    clock: Callable[[], datetime],
) -> FakeGovHttpApplication:
    if application is not None:
        return application
    return resolve_fake_http_application(runtime, clock=clock)
