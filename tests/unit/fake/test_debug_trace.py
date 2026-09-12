"""Security and resource contracts of the opt-in local debug observer."""

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from http.cookies import CookieError

import httpx
import pytest

from govbr_auth.adapters._application import create_adapter_application
from govbr_auth.fake.debug import redaction
from govbr_auth.fake.debug.controller import (
    DebugController,
    record_http_request,
    record_http_response,
)
from govbr_auth.fake.debug.trace import Trace, TraceStore
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 12, 5, tzinfo=UTC)


@pytest.fixture
def application():
    app = create_adapter_application(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        runtime=None,
        prefix="/auth/govbr",
        expose_tokens=False,
        clock=lambda: NOW,
        user_repository=None,
        fake_transport_factory=lambda fake: FakeGovHttpTransport(
            fake, clock=lambda: NOW
        ),
    )
    yield app
    asyncio.run(app.aclose())


def test_allowlist_redacts_secrets_unknown_fields_and_nested_values():
    secret = "PRIVATE-DATA-MARKER"
    projected = redaction.fields(
        {
            "state": secret,
            "nonce": secret,
            "name": secret,
            "access_token": secret,
            "unknown": secret,
            "error_description": secret,
            "code_verifier": secret,
            "response_type": ["code"],
            "grant_type": "authorization_code",
            "code_challenge_method": "S256",
            "token_type": "Bearer",
            "scope": "openid profile email openid",
            "keys": [{"n": secret}],
            "email": {"nested": secret},
            "aud": [],
            "iss": [secret, secret],
            "error": "invalid_grant",
        }
    )
    assert secret not in json.dumps(projected)
    assert "unknown" not in projected
    assert projected["response_type"] == "code"
    assert projected["state"] == "[oculto]"
    assert projected["scope"] == "openid profile email"
    assert projected["error"] == "invalid_grant"
    assert redaction.fields({"scope": "private_scope"}) == {"scope": "[oculto]"}


@pytest.mark.parametrize(
    ("content", "content_type", "expected"),
    (
        (
            b'{"access_token":"private"}',
            "application/json",
            {"access_token": "[oculto]"},
        ),
        (
            b"code=private&grant_type=authorization_code",
            "application/x-www-form-urlencoded",
            {"code": "[oculto]", "grant_type": "authorization_code"},
        ),
        (b"[]", "application/json", {"body": "[corpo não capturado]"}),
        (b"{", "application/json", {"body": "[corpo não capturado]"}),
        (
            b"\xff",
            "application/x-www-form-urlencoded",
            {"body": "[corpo não capturado]"},
        ),
        (b"<p>secret</p>", "text/html", {"body": "[corpo não capturado]"}),
        (
            b"a" * 65537,
            "application/json",
            {"body": "[corpo excede o limite de captura]"},
        ),
    ),
    # Keep raw bodies out of pytest node IDs and PYTEST_CURRENT_TEST on Windows.
    ids=(
        "json-object",
        "urlencoded-form",
        "json-array",
        "malformed-json",
        "invalid-utf8-form",
        "html-body",
        "oversized-body",
    ),
)
def test_body_projection_never_persists_unrecognized_content(
    content, content_type, expected
):
    assert redaction.body(content, content_type) == expected


def test_locations_remove_credentials_hosts_unknown_paths_and_query_secrets():
    paths = {"/authorize": "authorize"}
    result = redaction.location(
        "https://secret:secret@unknown.test/authorize?state=secret&unknown=secret",
        paths,
    )
    assert result == {"path": "/authorize", "query": {"state": "[oculto]"}}
    assert redaction.location("//[invalid", paths) == {"path": "[destino omitido]"}
    assert (
        redaction.location("https://unknown.test/private-path", paths)["path"]
        == "[destino omitido]"
    )


def test_headers_keep_only_known_semantics_and_cookie_attributes():
    values = [
        ("Authorization", "Basic private"),
        ("Cookie", "session=private"),
        (
            "Set-Cookie",
            "__Host-govbr-auth-private=private; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=0",
        ),
        ("Location", "/callback?code=private"),
        ("Content-Type", "application/json; secret=private"),
        ("Cache-Control", "no-store"),
        ("Pragma", "no-cache"),
        ("WWW-Authenticate", 'Bearer realm="private"'),
        ("X-Private", "private"),
    ]
    result = redaction.headers(values, {"/callback": "callback"})
    assert "private" not in json.dumps(result)
    assert result["Set-Cookie"] == [
        {
            "name": "prova do navegador",
            "value": "[oculto]",
            "HttpOnly": True,
            "Secure": True,
            "host_only": True,
            "Path": "/",
            "SameSite": "none",
            "removed": True,
        }
    ]
    hidden = redaction.headers(
        [
            ("Authorization", "Custom private"),
            ("Content-Type", "private"),
            ("Cache-Control", "private-data"),
            ("WWW-Authenticate", "Unknown private"),
            (
                "Set-Cookie",
                "other=private; Path=/private; Domain=private; SameSite=private",
            ),
        ],
        {},
    )
    assert "private" not in json.dumps(hidden)
    assert hidden["Set-Cookie"][0]["name"] == "cookie"
    assert hidden["Set-Cookie"][0]["host_only"] is False


def test_invalid_cookie_serializer_does_not_leak_or_break_the_observer(monkeypatch):
    def fail(self, value):
        raise CookieError("private-parser-marker")

    monkeypatch.setattr(redaction.SimpleCookie, "load", fail)
    assert redaction.headers([("Set-Cookie", "test=value")], {}) == {}


def test_trace_snapshots_are_independent_and_event_limit_is_explicit():
    clock = [0.0]
    trace = Trace(lambda: clock[0], max_events=2)
    number = trace.append("prepare", request={"query": {"state": "[oculto]"}})
    clock[0] = 0.123
    trace.finish(number, status=302)
    trace.inferred("binding")
    trace.inferred("validation")
    snapshot = trace.snapshot()
    assert snapshot["events"][0]["duration_ms"] == 123.0
    assert snapshot["events"][1]["duration_ms"] is None
    assert snapshot["truncated"] is True
    assert len(snapshot["events"]) == 2
    snapshot["events"][0]["request"]["query"]["state"] = "changed"
    assert trace.snapshot()["events"][0]["request"]["query"]["state"] == "[oculto]"


def test_store_limits_replacement_expiration_and_manual_removal():
    clock = [0.0]
    store = TraceStore(clock=lambda: clock[0], ttl=10, capacity=2)
    first, trace = store.start()
    second, _ = store.start()
    third, _ = store.start()
    assert store.get(first) is None
    assert store.get(second) is not None
    fourth, _ = store.start(third)
    assert store.get(third) is None
    store.stop(second)
    assert store.get(second) is None
    clock[0] = 10.0
    assert store.get(fourth) is None
    assert not store.traces
    assert first not in json.dumps(trace.snapshot())


def test_controller_refuses_official_runtime_and_deduplicates_http_hooks(application):
    one = DebugController(application)
    two = DebugController(application)
    http = application.runtime._owned_http
    assert http.event_hooks["request"].count(record_http_request) == 1
    assert http.event_hooks["response"].count(record_http_response) == 1
    application.runtime.provider = GovBrProvider.OFFICIAL
    with pytest.raises(ValueError, match="fake provider"):
        DebugController(application)
    application.runtime.provider = GovBrProvider.FAKE
    application.runtime._owned_http = None
    assert DebugController(application).origin == one.origin == two.origin
    application.runtime._owned_http = http


def test_controller_does_not_observe_unselected_or_unknown_requests(application):
    controller = DebugController(application)
    key, trace = controller.store.start()
    for path, cookies in (
        ("/auth/govbr/login", {}),
        ("/unknown", {controller.cookie_name: key}),
        ("/", {controller.cookie_name: key}),
    ):
        with controller.observe("GET", path, "", [], cookies) as capture:
            assert capture is None
    assert not trace.snapshot()["events"]
    with controller.observe(
        "PATCH", "/auth/govbr/login", "state=private", [], {controller.cookie_name: key}
    ) as capture:
        capture.finish(400, [])
        capture.finish(200, [])
    assert trace.snapshot()["events"][0]["status"] == "error"
    assert trace.snapshot()["events"][0]["request"]["method"] == "OTHER"


def test_exception_observation_does_not_invent_http_response_or_leak_text(application):
    controller = DebugController(application)
    key, trace = controller.store.start()
    with pytest.raises(RuntimeError, match="private-stack-marker"):
        with controller.observe(
            "GET",
            "/auth/govbr/callback",
            "code=private",
            [],
            {controller.cookie_name: key},
        ):
            raise RuntimeError("private-stack-marker")
    snapshot = trace.snapshot()
    assert snapshot["completed"] is True
    assert snapshot["events"][-1]["status"] == "error"
    assert snapshot["events"][-1]["response"] is None
    assert "private" not in json.dumps(snapshot)
    with controller.observe(
        "GET", "/auth/govbr/login", "", [], {controller.cookie_name: key}
    ) as capture:
        assert capture is None


@pytest.mark.asyncio
async def test_hooks_are_inert_without_opt_in_and_skip_unknown_endpoints(application):
    request = httpx.Request("GET", "http://127.0.0.1:8000/unrelated")
    response = httpx.Response(200, json={"name": "private"}, request=request)
    await record_http_request(request)
    await record_http_response(response)
    controller = DebugController(application)
    key, trace = controller.store.start()
    with controller.observe(
        "GET", "/auth/govbr/login", "", [], {controller.cookie_name: key}
    ) as capture:
        await record_http_request(request)
        await record_http_response(response)
        capture.finish(302, [])
    assert "govbr_demo_event" not in request.extensions
    assert [e["phase"] for e in trace.snapshot()["events"]] == ["prepare"]


@pytest.mark.asyncio
async def test_callback_without_http_response_marks_pending_event_as_unobserved(
    application,
):
    controller = DebugController(application)
    key, trace = controller.store.start()
    with controller.observe(
        "GET", "/auth/govbr/callback", "", [], {controller.cookie_name: key}
    ) as capture:
        request = httpx.Request(
            "POST", "http://127.0.0.1:8000/fake-govbr/token", data={"code": "private"}
        )
        await record_http_request(request)
        capture.finish(503, [])
    token = next(e for e in trace.snapshot()["events"] if e["phase"] == "token")
    assert token["status"] == "error" and token["response"] is None
    assert trace.snapshot()["events"][-1]["response"]["status"] == 503


def test_controller_does_not_invent_a_disabled_consumer_logout(application):
    application.logout_path = None
    controller = DebugController(application)
    assert "/auth/govbr/logout" not in controller.paths
    assert controller.paths["/fake-govbr/logout"] == "logout"


def test_full_trace_can_finish_callback_without_allocating_more_events(application):
    controller = DebugController(application)
    key, trace = controller.store.start()
    trace.max_events = 1
    trace.append("prepare")
    with controller.observe(
        "GET", "/auth/govbr/callback", "code=private", [], {controller.cookie_name: key}
    ) as capture:
        capture.finish(400, [])
    snapshot = trace.snapshot()
    assert snapshot["completed"] is True
    assert snapshot["truncated"] is True
    assert len(snapshot["events"]) == 1
    assert snapshot["events"][0]["status"] == "error"
    assert "private" not in json.dumps(snapshot)


def test_fastapi_instrumentation_preserves_non_api_routes(application):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from govbr_auth.fake.debug.fastapi import observe_router

    async def health(request):
        return PlainTextResponse("healthy")

    original = Route("/health", health)
    router = APIRouter(routes=[original])
    observed = observe_router(router, DebugController(application))
    assert observed.routes == [original]
    app = FastAPI()
    app.include_router(observed)
    with TestClient(app) as browser:
        response = browser.get("/health")
    assert response.status_code == 200
    assert response.text == "healthy"
