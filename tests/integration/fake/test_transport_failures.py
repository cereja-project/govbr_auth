"""Exercise malformed requests and failures without contacting an external provider."""

import base64
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.formparsers import MultiPartException

from govbr_auth.fake.http.application import LoginResult
from govbr_auth.fake.http.routes import build_fake_govbr_routes
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.fake.provider import FakeAuthorizationSession, FakeOAuthError
from govbr_auth.fake.runtime import create_fake_gov_simulator
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


@pytest.fixture
def simulator():
    return create_fake_gov_simulator(
        GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        prefix="/fake-govbr",
        clock=lambda: NOW,
    )


def _basic(simulator):
    client = simulator.settings.clients[0]
    credentials = f"{client.client_id}:{client.client_secret.get_secret_value()}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("GET", "/fake-govbr/token"),
        ("POST", "/fake-govbr/jwk"),
        ("POST", "/fake-govbr/userinfo"),
        ("GET", "/fake-govbr/not-a-route"),
    ),
)
async def test_transport_rejects_unsupported_routes_and_methods(
    simulator, method, path
):
    transport = FakeGovHttpTransport(simulator, clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as http:
        response = await http.request(method, path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "method", "status", "error", "challenge"),
    (
        ("token", "POST", 401, "invalid_client", 'Basic realm="fake-govbr"'),
        ("userinfo", "GET", 401, "invalid_token", "Bearer"),
    ),
)
async def test_transport_requires_client_or_bearer_credentials(
    simulator, route, method, status, error, challenge
):
    transport = FakeGovHttpTransport(simulator, clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as http:
        response = await http.request(method, f"/fake-govbr/{route}")
    assert response.status_code == status
    assert response.json()["error"] == error
    assert response.headers["WWW-Authenticate"] == challenge
    if route == "token":
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ("token", "userinfo"))
@pytest.mark.parametrize(
    ("error", "status", "challenge"),
    (
        ("invalid_client", 401, 'Basic realm="fake-govbr"'),
        ("invalid_token", 401, "Bearer"),
        ("access_denied", 403, None),
        ("invalid_request", 400, None),
    ),
)
async def test_transport_preserves_error_status_and_cache_contracts(
    simulator, monkeypatch, route, error, status, challenge
):
    def fail(*args, **kwargs):
        raise FakeOAuthError(error=error, description="Controlled provider failure.")

    monkeypatch.setattr(simulator.http_application, route, fail)
    transport = FakeGovHttpTransport(simulator, clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as http:
        response = await http.request(
            "POST" if route == "token" else "GET",
            f"/fake-govbr/{route}",
            headers=_basic(simulator),
        )
    assert response.status_code == status
    assert response.json() == {
        "error": error,
        "error_description": "Controlled provider failure.",
    }
    assert response.headers.get("WWW-Authenticate") == challenge
    if route == "token" or error == "invalid_client":
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"
    else:
        assert "Cache-Control" not in response.headers


@pytest.mark.asyncio
async def test_transport_rejects_non_utf8_token_form(simulator):
    transport = FakeGovHttpTransport(simulator, clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as http:
        response = await http.post(
            "/fake-govbr/token",
            headers=_basic(simulator),
            content=b"code=\xff\xfe",
        )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "failure",
    (
        MultiPartException("private-parser-detail"),
        ValueError("private-parser-detail"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid input"),
    ),
)
def test_fastapi_routes_reject_unreadable_forms_without_exposing_parser_errors(
    simulator, monkeypatch, failure
):
    async def fail_form(self):
        raise failure

    monkeypatch.setattr(Request, "form", fail_form)
    app = FastAPI()
    app.include_router(
        build_fake_govbr_routes(simulator, automatic_subject=None, clock=lambda: NOW)
    )
    with TestClient(app) as client:
        response = client.post("/fake-govbr/login", data={"request": "opaque"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert "private-parser-detail" not in response.text
    assert "opaque" not in response.text


def test_fastapi_provider_rejects_inconsistent_success_result(simulator, monkeypatch):
    session = FakeAuthorizationSession(request=SecretStr("test-artifact"))
    monkeypatch.setattr(
        simulator.http_application,
        "login",
        lambda values: LoginResult(session=session, redirect=None),
    )
    app = FastAPI()
    app.include_router(
        build_fake_govbr_routes(simulator, automatic_subject=None, clock=lambda: NOW)
    )
    with TestClient(app) as client:
        with pytest.raises(RuntimeError, match="must include a redirect"):
            client.post("/fake-govbr/login")
