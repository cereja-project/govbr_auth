"""Verify consumer callback failures through each framework's HTTP boundary."""

import importlib
from contextlib import ExitStack
from datetime import UTC, datetime
from types import ModuleType
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


@pytest.fixture(params=("django", "flask", "fastapi"))
def consumer_factory(request):
    with ExitStack() as stack:

        def build(*, custom_errors=False):
            framework = request.param
            module = importlib.import_module(f"govbr_auth.{framework}")
            received = []

            def respond(payload, status):
                if framework == "django":
                    from django.http import JsonResponse

                    return JsonResponse(payload, status=status)
                if framework == "flask":
                    from flask import jsonify

                    return jsonify(payload), status
                from fastapi.responses import JSONResponse

                return JSONResponse(payload, status_code=status)

            def on_error(error, request=None):
                received.append(error)
                return respond({"custom": True, "error": error.code}, 418)

            async def async_error(error):
                return on_error(error)

            def on_success(context, request=None):
                raise AssertionError("an invalid callback must not authenticate")

            async def async_success(context):
                return on_success(context)

            handler = async_error if framework == "fastapi" else on_error
            auth = module.GovBrAuth(
                settings=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
                on_success=async_success if framework == "fastapi" else on_success,
                on_error=handler if custom_errors else None,
                clock=lambda: NOW,
            )
            if framework == "django":
                import django
                from django.conf import settings
                from django.test import Client, override_settings
                from django.urls import clear_url_caches

                if not settings.configured:
                    settings.configure(SECRET_KEY="tests-only")
                django.setup()
                urls = ModuleType("consumer_callback_error_urls")
                urls.urlpatterns = auth.urlpatterns
                stack.enter_context(
                    override_settings(
                        ROOT_URLCONF=urls,
                        ALLOWED_HOSTS=["testserver"],
                        MIDDLEWARE=[],
                    )
                )
                clear_url_caches()
                stack.callback(clear_url_caches)
                stack.callback(auth.close)
                client = Client()

                def send(path):
                    response = client.get(path)
                    return httpx.Response(
                        response.status_code,
                        headers=dict(response.headers),
                        content=response.content,
                    )

            elif framework == "flask":
                from flask import Flask

                app = Flask(__name__)
                app.config["TESTING"] = True
                auth.register(app)
                stack.callback(auth.close)
                client = app.test_client()

                def send(path):
                    response = client.get(path)
                    return httpx.Response(
                        response.status_code,
                        headers=dict(response.headers),
                        content=response.data,
                    )

            else:
                from fastapi import FastAPI
                from fastapi.testclient import TestClient

                app = FastAPI()
                app.include_router(auth.router)
                client = stack.enter_context(TestClient(app))

                def send(path):
                    return client.get(path, follow_redirects=False)

            return auth, send, received

        yield build


def _callback(send, values):
    return send("/auth/govbr/callback?" + urlencode(values))


@pytest.mark.parametrize(
    "values",
    (
        {},
        {"code": " ", "state": "present"},
        {"code": "present"},
        {"code": "present", "state": " "},
        {"error": " ", "state": "present"},
        {"error": "access_denied"},
        {"error": "access_denied", "state": " "},
    ),
)
def test_malformed_callbacks_never_reach_user_hooks(consumer_factory, values):
    _, send, received = consumer_factory(custom_errors=True)
    response = _callback(send, values)
    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_callback",
        "message": "Callback parameters are invalid.",
    }
    assert received == []


@pytest.mark.parametrize("custom_errors", (False, True))
def test_provider_rejection_is_sanitized_or_delivered_to_error_hook(
    consumer_factory, custom_errors
):
    _, send, received = consumer_factory(custom_errors=custom_errors)
    login = send("/auth/govbr/login")
    state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
    response = _callback(
        send,
        {
            "error": "access_denied",
            "state": state,
            "error_description": "sensitive-provider-description-marker",
        },
    )
    assert response.status_code == (418 if custom_errors else 502)
    assert response.json()["error"] == "provider_rejected"
    assert "sensitive-provider-description-marker" not in response.text
    assert state not in response.text
    assert [error.code for error in received] == (
        ["provider_rejected"] if custom_errors else []
    )


@pytest.mark.parametrize("custom_errors", (False, True))
def test_invalid_state_is_sanitized_or_delivered_to_error_hook(
    consumer_factory, custom_errors
):
    _, send, received = consumer_factory(custom_errors=custom_errors)
    response = _callback(send, {"code": "code-marker", "state": "invalid-state"})
    assert response.status_code == (418 if custom_errors else 400)
    assert response.json()["error"] == "invalid_state"
    assert "code-marker" not in response.text
    assert [error.code for error in received] == (
        ["invalid_state"] if custom_errors else []
    )


def test_callback_fails_closed_if_provider_error_service_returns(
    consumer_factory, monkeypatch
):
    auth, send, received = consumer_factory()
    monkeypatch.setattr(
        auth._application.service, "provider_error", lambda **kwargs: None
    )
    with pytest.raises(AssertionError, match="provider_error must raise"):
        _callback(send, {"error": "access_denied", "state": "present"})
    assert received == []


@pytest.mark.parametrize("framework", ("django", "flask", "fastapi"))
def test_adapter_default_clock_returns_current_utc(framework):
    module = importlib.import_module(f"govbr_auth.{framework}")
    before = datetime.now(UTC)
    current = module.utc_now()
    after = datetime.now(UTC)
    assert before <= current <= after
    assert current.tzinfo is UTC


@pytest.mark.parametrize("framework", ("django", "flask"))
def test_native_adapter_rejects_noncanonical_prefix_before_composition(framework):
    module = importlib.import_module(f"govbr_auth.{framework}")
    with pytest.raises(ValueError, match="canonical path"):
        module.GovBrAuth(on_success=lambda *args: None, prefix="/invalid//prefix")


@pytest.mark.parametrize("framework", ("django", "flask"))
def test_native_adapter_rejects_ambiguous_runtime_ownership(framework):
    module = importlib.import_module(f"govbr_auth.{framework}")
    with pytest.raises(TypeError, match="mutually exclusive"):
        module.GovBrAuth(
            on_success=lambda *args: None,
            settings=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
            runtime=object(),
        )
