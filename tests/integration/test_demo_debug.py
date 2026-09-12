"""Observe the real local flow without retaining its authentication material."""

import json
import re
from datetime import UTC, datetime

import pytest
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from govbr_auth.fake import create_fake_app
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings
from tests.integration.browser_support import browser_application

DEBUG = "/govbr-auth-demo/debug"
HEADERS = {"X-Govbr-Demo": "1", "Origin": "http://127.0.0.1:8000"}


def test_debug_page_is_available_from_the_local_demo():
    app = create_fake_app(GovBrRuntimeSettings(provider=GovBrProvider.FAKE))
    with TestClient(app, base_url="http://127.0.0.1:8000") as browser:
        home = browser.get("/")
        page = browser.get(DEBUG)
    assert DEBUG in home.text
    assert page.status_code == 200
    assert "Painel técnico" in page.text
    assert "Modo debug" in page.text


def test_real_login_produces_a_private_redacted_trace():
    app = create_fake_app(GovBrRuntimeSettings(provider=GovBrProvider.FAKE))
    with TestClient(app, base_url="http://127.0.0.1:8000") as browser:
        started = browser.post(DEBUG + "/trace", headers=HEADERS)
        assert started.status_code == 201
        login = browser.get("/auth/govbr/login", follow_redirects=False)
        values = parse_qs(urlsplit(login.headers["location"]).query)
        auth_page = browser.get(login.headers["location"])
        artifact = re.search(r'name="request" value="([^"]+)"', auth_page.text)[1]
        provider = browser.post(
            "/fake-govbr/login",
            data={
                "request": artifact,
                "cpf": "11122233344",
                "password": "senha-ficticia",
            },
            follow_redirects=False,
        )
        assert provider.status_code == 302
        callback_values = parse_qs(urlsplit(provider.headers["location"]).query)
        result = browser.get(provider.headers["location"])
        assert result.status_code == 200
        snapshot = browser.get(DEBUG + "/trace", headers=HEADERS)
        assert snapshot.status_code == 200
        trace = snapshot.json()
        phases = [event["phase"] for event in trace["events"]]
        for phase in (
            "prepare",
            "authorize",
            "provider_login",
            "callback",
            "token",
            "jwks",
            "userinfo",
            "result",
        ):
            assert phase in phases
        rendered = json.dumps(trace)
        for secret in (
            values["state"][0],
            values["nonce"][0],
            artifact,
            callback_values["code"][0],
            "11122233344",
            "senha-ficticia",
        ):
            assert secret not in rendered
        with TestClient(app, base_url="http://127.0.0.1:8000") as outsider:
            assert outsider.get(DEBUG + "/trace", headers=HEADERS).status_code == 404
        assert browser.delete(DEBUG + "/trace", headers=HEADERS).status_code == 204
        assert browser.get(DEBUG + "/trace", headers=HEADERS).status_code == 404


NOW = datetime(2026, 9, 12, 5, tzinfo=UTC)


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_each_native_adapter_observes_full_flow_without_exposing_secrets(framework):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        _,
        browsers,
        _,
    ):
        browser, outsider = browsers(), browsers()
        assert browser(DEBUG).status_code == 200
        assert browser(DEBUG + "/trace", headers=HEADERS).status_code == 404
        started = browser(DEBUG + "/trace", method="POST", headers=HEADERS)
        assert started.status_code == 201
        assert "httponly" in started.headers["set-cookie"].lower()
        assert "domain=" not in started.headers["set-cookie"].lower()
        login = browser("/auth/govbr/login")
        assert login.status_code == 302
        values = parse_qs(urlsplit(login.headers["location"]).query)
        form = browser(login.headers["location"])
        artifact = re.search(r'name="request" value="([^"]+)"', form.text)[1]
        failed = browser(
            "/fake-govbr/login",
            method="POST",
            data={
                "request": artifact,
                "cpf": "11122233344",
                "password": "a-private-password-marker",
            },
        )
        assert failed.status_code == 401
        interim = browser(DEBUG + "/trace", headers=HEADERS).json()
        assert interim["events"][-1]["phase"] == "provider_login"
        assert interim["events"][-1]["status"] == "error"
        assert interim["completed"] is False
        authorized = browser(
            "/fake-govbr/login",
            method="POST",
            data={
                "request": artifact,
                "cpf": "11122233344",
                "password": "senha-ficticia",
            },
        )
        callback = browser(authorized.headers["location"])
        assert callback.status_code == 200
        snapshot = browser(DEBUG + "/trace", headers=HEADERS)
        assert snapshot.status_code == 200
        assert snapshot.headers["cache-control"] == "no-store"
        trace = snapshot.json()
        phases = [event["phase"] for event in trace["events"]]
        assert phases == [
            "prepare",
            "authorize",
            "provider_login",
            "provider_login",
            "callback",
            "binding",
            "token",
            "jwks",
            "validation",
            "userinfo",
            "result",
        ]
        assert trace["completed"] is True
        assert all(
            event["duration_ms"] is None
            for event in trace["events"]
            if event["evidence"] == "inferred"
        )
        assert (
            trace["events"][-1]["response"]["headers"]["Set-Cookie"][0]["removed"]
            is True
        )
        for secret in (
            artifact,
            values["state"][0],
            values["nonce"][0],
            "a-private-password-marker",
            "senha-ficticia",
            "11122233344",
            "fake@example.test",
            "Usuário Fake",
        ):
            assert secret not in json.dumps(trace, ensure_ascii=False)
        token_event = next(e for e in trace["events"] if e["phase"] == "token")
        assert token_event["request"]["body"]["code_verifier"] == "[oculto]"
        assert token_event["response"]["body"]["access_token"] == "[oculto]"
        assert token_event["request"]["headers"]["Authorization"] == "Basic [oculto]"
        assert outsider(DEBUG + "/trace", headers=HEADERS).status_code == 404
        assert (
            browser(DEBUG + "/trace", method="DELETE", headers=HEADERS).status_code
            == 204
        )
        assert browser(DEBUG + "/trace", headers=HEADERS).status_code == 404


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_trace_control_rejects_cross_origin_and_never_creates_implicit_capture(
    framework,
):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        _,
        browsers,
        _,
    ):
        browser = browsers()
        browser("/auth/govbr/login")
        assert browser(DEBUG + "/trace", headers=HEADERS).status_code == 404
        for method in ("GET", "POST", "DELETE"):
            denied = browser(
                DEBUG + "/trace",
                method=method,
                headers={"X-Govbr-Demo": "1", "Origin": "https://foreign.example.test"},
            )
            assert denied.status_code == 403
            assert "access-control-allow-origin" not in denied.headers
            assert browser(DEBUG + "/trace", method=method).status_code == 403
        assert (
            browser(
                DEBUG + "/trace", method="POST", headers={"X-Govbr-Demo": "1"}
            ).status_code
            == 403
        )
        assert (
            browser(DEBUG + "/trace", method="POST", headers=HEADERS).status_code == 201
        )
        assert (
            browser(DEBUG + "/trace", headers={"X-Govbr-Demo": "1"}).status_code == 200
        )


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
@pytest.mark.parametrize(
    "query", ("?code=secret-marker", "?code=secret-marker&state=forged-private-marker")
)
def test_invalid_callback_is_visible_without_inventing_later_validations(
    framework, query
):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        _,
        browsers,
        _,
    ):
        browser = browsers()
        browser(DEBUG + "/trace", method="POST", headers=HEADERS)
        result = browser("/auth/govbr/callback" + query)
        assert result.status_code == 400
        trace = browser(DEBUG + "/trace", headers=HEADERS).json()
        assert [e["phase"] for e in trace["events"]] == ["callback", "result"]
        assert trace["events"][-1]["status"] == "error"
        assert "secret-marker" not in json.dumps(trace)
        assert "forged-private-marker" not in json.dumps(trace)


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_debug_routes_do_not_exist_with_official_provider(framework):
    from govbr_auth.core.settings import GovBrSettings

    fake = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    values = fake.oauth.model_dump()
    origin = "https://sso.staging.acesso.gov.br"
    values.update(
        environment="staging",
        authorization_url=origin + "/authorize",
        token_url=origin + "/token",
        userinfo_url=origin + "/userinfo/",
        issuer=origin + "/",
        jwks_url=origin + "/jwk",
        logout_url=None,
        post_logout_redirect_uri=None,
    )
    settings = GovBrRuntimeSettings(
        provider=GovBrProvider.OFFICIAL, oauth=GovBrSettings.model_validate(values)
    )
    with browser_application(framework, settings, clock=lambda: NOW) as (
        auth,
        browsers,
        _,
    ):
        browser = browsers()
        assert browser(DEBUG).status_code == 404
        assert (
            browser(DEBUG + "/trace", method="POST", headers=HEADERS).status_code == 404
        )
        assert auth._application.runtime._owned_http.event_hooks == {
            "request": [],
            "response": [],
        }
