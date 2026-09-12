"""Verify launcher failures and keep official runtimes separate from the demo."""

import asyncio
import runpy
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from flask import Flask

from govbr_auth import fake
from govbr_auth.core.errors import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidIdTokenError,
    InvalidStateError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.fake.launcher import create_end_to_end_app, public_error
from govbr_auth.flask import GovBrAuth
from govbr_auth.presentation import _render_demo_shell, render_primary_action
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings, create_govbr_runtime

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


@pytest.fixture
def official_runtime():
    values = GovBrRuntimeSettings(provider=GovBrProvider.FAKE).oauth.model_dump()
    origin = "https://sso.staging.acesso.gov.br"
    values.update(
        environment="staging",
        authorization_url=f"{origin}/authorize",
        token_url=f"{origin}/token",
        userinfo_url=f"{origin}/userinfo/",
        issuer=f"{origin}/",
        jwks_url=f"{origin}/jwk",
        logout_url=None,
        post_logout_redirect_uri=None,
    )
    settings = GovBrRuntimeSettings(
        provider=GovBrProvider.OFFICIAL,
        oauth=GovBrSettings.model_validate(values),
    )
    runtime = create_govbr_runtime(settings)
    try:
        yield runtime
    finally:
        asyncio.run(runtime.aclose())


def test_official_flask_registration_exposes_no_fake_routes(official_runtime):
    auth = GovBrAuth(runtime=official_runtime, on_success=lambda *args: "unused")
    app = Flask(__name__)
    auth.register(app)
    assert auth.blueprint.name == "govbr_auth"
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/auth/govbr/login" in routes
    assert "/auth/govbr/callback" in routes
    assert "/auth/govbr/logout" not in routes
    assert "/" not in routes
    assert not any(route.startswith("/fake-govbr") for route in routes)
    response = app.test_client().get("/auth/govbr/login")
    assert response.status_code == 302
    assert response.headers["Location"].startswith(
        "https://sso.staging.acesso.gov.br/authorize?"
    )
    auth.close()
    assert not official_runtime.is_closed


def test_end_to_end_launcher_rejects_official_provider(official_runtime):
    with pytest.raises(RuntimeError, match="requires the fake provider runtime"):
        create_end_to_end_app(official_runtime, clock=lambda: NOW)
    assert not official_runtime.is_closed


@pytest.mark.parametrize(
    ("error_type", "code", "status"),
    (
        (InvalidStateError, "invalid_state", 400),
        (ExpiredTransactionError, "expired_transaction", 400),
        (InvalidIdTokenError, "invalid_id_token", 502),
        (ProviderRejectedError, "provider_rejected", 502),
        (ProviderUnavailableError, "provider_unavailable", 503),
        (GovBrAuthError, "govbr_auth_error", 502),
    ),
)
def test_launcher_public_error_mapping_never_contains_exception_details(
    error_type, code, status
):
    assert public_error(error_type("private-exception-marker")) == (code, status)


def test_launcher_handles_framework_validation_errors_with_safe_html():
    runtime = create_govbr_runtime(
        GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        fake_transport_factory=lambda simulator: FakeGovHttpTransport(
            simulator, clock=lambda: NOW
        ),
        clock=lambda: NOW,
    )
    rendered = []

    def render_error(*, code, status_code):
        rendered.append((code, status_code))
        return f"<p>{code}</p>"

    app = create_end_to_end_app(
        runtime, clock=lambda: NOW, render_error_page=render_error
    )

    @app.get("/validation-probe/{value}")
    def probe(value: int):
        return {"value": value}

    with TestClient(app) as client:
        valid = client.get("/validation-probe/1")
        invalid = client.get("/validation-probe/private-input-marker")
    assert valid.status_code == 200
    assert valid.json() == {"value": 1}
    assert invalid.status_code == 400
    assert invalid.text == "<p>invalid_callback</p>"
    assert invalid.headers["Cache-Control"] == "no-store"
    assert invalid.headers["Content-Type"].startswith("text/html")
    assert rendered == [("invalid_callback", 400)]
    assert runtime.is_closed


def test_importing_launcher_entrypoint_does_not_start_a_server(monkeypatch):
    def unexpected_start():
        pytest.fail("importing the module must not start a server")

    monkeypatch.setattr(fake, "run", unexpected_start)
    namespace = runpy.run_module(
        "govbr_auth.fake.__main__", run_name="govbr_auth_test_import"
    )
    assert namespace["__name__"] == "govbr_auth_test_import"
    assert namespace["run"] is unexpected_start


def test_interactive_demo_rejects_missing_login_destination():
    with pytest.raises(ValueError, match="interactive demo requires a login path"):
        _render_demo_shell(
            badge="",
            provider_copy="",
            action="",
            interactive=True,
            login_path=None,
            footer="",
        )


def test_primary_action_rejects_malformed_authority():
    with pytest.raises(ValueError, match="internal absolute path") as caught:
        render_primary_action(href="//[invalid-ipv6", label="Continue")
    assert isinstance(caught.value.__cause__, ValueError)
