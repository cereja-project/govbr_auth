"""Exercise the native Django and Flask provider routes over real HTTP clients."""

import base64
import hashlib
import re
from contextlib import ExitStack
from datetime import UTC, datetime
from types import ModuleType
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from govbr_auth.fake.http.application import LoginResult
from govbr_auth.fake.provider import FakeOAuthError
from govbr_auth.fake.runtime import create_fake_gov_simulator
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)
VERIFIER = "native-provider-verifier-abcdefghijklmnopqrstuvwxyz0123456789"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode("ascii")).digest())
    .rstrip(b"=")
    .decode("ascii")
)


@pytest.fixture(params=("django", "flask"))
def native_client_factory(request):
    """Keep each framework's routing and settings isolated between scenarios."""
    with ExitStack() as stack:

        def build(simulator, *, application=None):
            if request.param == "django":
                import django
                from django.conf import settings
                from django.test import Client, override_settings
                from django.urls import clear_url_caches
                from govbr_auth.fake.django import create_fake_govbr_urlpatterns

                if not settings.configured:
                    settings.configure(SECRET_KEY="tests-only")
                django.setup()
                urls = ModuleType("native_fake_provider_urls")
                urls.urlpatterns = create_fake_govbr_urlpatterns(
                    simulator, clock=lambda: NOW, application=application
                )
                stack.enter_context(
                    override_settings(
                        ROOT_URLCONF=urls,
                        ALLOWED_HOSTS=["testserver"],
                        MIDDLEWARE=[],
                    )
                )
                clear_url_caches()
                stack.callback(clear_url_caches)
                client = Client()

                def send(method, path, *, data=None, headers=None):
                    call = getattr(client, method.lower())
                    response = call(path, data=data or {}, headers=headers or {})
                    return httpx.Response(
                        response.status_code,
                        headers=dict(response.headers),
                        content=response.content,
                    )

            else:
                from flask import Flask
                from govbr_auth.fake.flask import create_fake_govbr_blueprint

                app = Flask(__name__)
                app.config["TESTING"] = True
                app.register_blueprint(
                    create_fake_govbr_blueprint(
                        simulator, clock=lambda: NOW, application=application
                    )
                )
                client = app.test_client()

                def send(method, path, *, data=None, headers=None):
                    response = client.open(
                        path, method=method, data=data, headers=headers
                    )
                    return httpx.Response(
                        response.status_code,
                        headers=dict(response.headers),
                        content=response.data,
                    )

            return send

        yield build


@pytest.fixture
def simulator():
    return create_fake_gov_simulator(
        GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        prefix="/fake-govbr",
        clock=lambda: NOW,
    )


def _authorization(simulator):
    client = simulator.settings.clients[0]
    return {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": str(client.registered_redirect_uris[0]),
        "scope": "openid profile email",
        "state": "native-state",
        "nonce": "native-nonce",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }


def _basic(simulator):
    client = simulator.settings.clients[0]
    pair = f"{client.client_id}:{client.client_secret.get_secret_value()}"
    return {"Authorization": "Basic " + base64.b64encode(pair.encode()).decode()}


def _artifact(response):
    match = re.search(r'name="request" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize("prefix", ("", "/fake-govbr"))
def test_native_provider_completes_flow_and_rejects_code_replay(
    native_client_factory, prefix
):
    simulator = create_fake_gov_simulator(
        GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        prefix=prefix,
        clock=lambda: NOW,
    )
    send = native_client_factory(simulator)
    query = _authorization(simulator)
    authorize = send("GET", f"{prefix}/authorize?{urlencode(query)}")
    assert authorize.status_code == 200
    assert authorize.headers["Cache-Control"] == "no-store"
    assert f'action="{prefix}/login"' in authorize.text
    form = {
        "request": _artifact(authorize),
        "cpf": "11122233344",
        "password": "senha-ficticia",
    }

    rejected = send("POST", f"{prefix}/login", data={**form, "password": "wrong"})
    assert rejected.status_code == 401
    assert rejected.headers["Cache-Control"] == "no-store"
    assert _artifact(rejected) == form["request"]

    login = send("POST", f"{prefix}/login", data=form)
    assert login.status_code == 302
    values = parse_qs(urlsplit(login.headers["Location"]).query)
    assert values["state"] == [query["state"]]
    token_data = {
        "grant_type": "authorization_code",
        "code": values["code"][0],
        "redirect_uri": query["redirect_uri"],
        "code_verifier": VERIFIER,
    }
    token = send("POST", f"{prefix}/token", data=token_data, headers=_basic(simulator))
    assert token.status_code == 200
    assert token.headers["Cache-Control"] == "no-store"
    assert token.headers["Pragma"] == "no-cache"
    tokens = token.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["id_token"]
    assert tokens["expires_in"] > 0
    assert tokens["scope"] == query["scope"]

    keys = send("GET", f"{prefix}/jwk")
    assert keys.status_code == 200
    assert len(keys.json()["keys"]) == 1
    assert "d" not in keys.json()["keys"][0]
    user = send(
        "GET",
        f"{prefix}/userinfo",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert user.status_code == 200
    assert user.json()["sub"] == form["cpf"]
    assert "password" not in user.json()

    target = str(simulator.settings.post_logout_redirect_uris[0])
    logout = send(
        "GET", f"{prefix}/logout?{urlencode({'post_logout_redirect_uri': target})}"
    )
    assert logout.status_code == 302
    assert logout.headers["Location"] == target
    replay = send("POST", f"{prefix}/token", data=token_data, headers=_basic(simulator))
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"
    assert replay.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("method", "route", "status", "error"),
    (
        ("GET", "authorize", 400, "invalid_request"),
        ("POST", "login", 400, "invalid_request"),
        ("POST", "token", 400, "invalid_request"),
        ("GET", "userinfo", 401, "invalid_token"),
        ("GET", "logout", 400, "invalid_request"),
    ),
)
def test_native_provider_rejects_missing_http_inputs(
    native_client_factory, simulator, method, route, status, error
):
    send = native_client_factory(simulator)
    headers = _basic(simulator) if route == "token" else {}
    response = send(method, f"{simulator.prefix}/{route}", headers=headers)
    assert response.status_code == status
    assert response.json()["error"] == error


@pytest.mark.parametrize("route", ("authorize", "token"))
@pytest.mark.parametrize(
    ("error", "status", "challenge"),
    (
        ("invalid_client", 401, 'Basic realm="fake-govbr"'),
        ("invalid_token", 401, "Bearer"),
        ("access_denied", 403, None),
        ("invalid_request", 400, None),
    ),
)
def test_native_provider_preserves_oauth_error_http_contract(
    native_client_factory, simulator, monkeypatch, route, error, status, challenge
):
    def reject(*args, **kwargs):
        raise FakeOAuthError(error=error, description="Controlled provider failure.")

    application = simulator.http_application
    monkeypatch.setattr(application, route, reject)
    send = native_client_factory(simulator, application=application)
    method = "POST" if route == "token" else "GET"
    response = send(method, f"{simulator.prefix}/{route}", headers=_basic(simulator))
    assert response.status_code == status
    assert response.json() == {
        "error": error,
        "error_description": "Controlled provider failure.",
    }
    assert response.headers.get("WWW-Authenticate") == challenge
    if route == "token":
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"


def test_native_provider_accepts_automatic_authorization(
    native_client_factory, simulator, monkeypatch
):
    application = simulator.http_application
    authorize = application.authorize
    monkeypatch.setattr(
        application,
        "authorize",
        lambda values: authorize(values, automatic_subject="11122233344"),
    )
    send = native_client_factory(simulator, application=application)
    query = urlencode(_authorization(simulator))
    response = send("GET", f"{simulator.prefix}/authorize?{query}")
    assert response.status_code == 302
    values = parse_qs(urlsplit(response.headers["Location"]).query)
    assert values["code"][0]
    assert values["state"] == ["native-state"]


def test_native_provider_fails_closed_on_inconsistent_login_result(
    native_client_factory, simulator, monkeypatch
):
    application = simulator.http_application
    session = application.authorize(_authorization(simulator)).session
    monkeypatch.setattr(
        application, "login", lambda values: LoginResult(session=session, redirect=None)
    )
    send = native_client_factory(simulator, application=application)
    with pytest.raises(RuntimeError, match="must include a redirect"):
        send("POST", f"{simulator.prefix}/login")
