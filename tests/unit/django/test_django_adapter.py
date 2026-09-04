"""Unit contract for the native Django consumer adapter."""

from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import Resolver404, resolve
from pydantic import SecretStr

if not settings.configured:
    settings.configure(
        ALLOWED_HOSTS=["testserver"],
        DEFAULT_CHARSET="utf-8",
        SECRET_KEY="tests-only",
    )

import django

django.setup()

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
    create_govbr_runtime,
)

FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class ContractClient:
    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = dict(claims)
        self.tokens = TokenSet(
            access_token=SecretStr("access-token"),
            id_token=SecretStr("id-token"),
            token_type="Bearer",
            expires_in=300,
            scope="openid profile email",
        )

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        return AuthorizationRequest("https://sso.example.test/authorize", "state")

    async def exchange_code(
        self, *, code: str, state: str, now: datetime
    ) -> AuthenticationResult:
        return AuthenticationResult(tokens=self.tokens, id_token_claims=self.claims)

    async def userinfo(
        self, access_token: SecretStr, *, expected_subject: str
    ) -> GovBrUser:
        return GovBrUser(sub=expected_subject, name="Django user")


def _runtime(
    client: ContractClient,
    *,
    redirect_uri: str | None = None,
) -> GovBrRuntime:
    oauth = None
    if redirect_uri is not None:
        oauth = GovBrSettings(
            authorization_url="https://sso.example.test/authorize",
            token_url="https://sso.example.test/token",
            userinfo_url="https://sso.example.test/userinfo",
            client_id="client-id",
            client_secret=SecretStr("client-secret"),
            redirect_uri=redirect_uri,
            transaction_secret=SecretStr("transaction-secret"),
            issuer="https://sso.example.test/",
            jwks_url="https://sso.example.test/jwks",
        )
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL, oauth=oauth),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=None,
    )


def _route(auth: object, suffix: str):
    return next(
        pattern.callback
        for pattern in auth.urlpatterns
        if str(pattern.pattern).endswith(suffix)
    )


def _fake_runtime_settings() -> GovBrRuntimeSettings:
    return GovBrRuntimeSettings(provider=GovBrProvider.FAKE)


def _colliding_fake_runtime() -> GovBrRuntime:
    return create_govbr_runtime(
        GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_provider_prefix="/auth/govbr",
        ),
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda __: httpx.Response(500)
        ),
        clock=lambda: FIXED_NOW,
    )


def test_django_facade_exposes_native_login_and_callback_patterns() -> None:
    from govbr_auth.django import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    assert [str(pattern.pattern) for pattern in auth.urlpatterns] == [
        "auth/govbr/login",
        "auth/govbr/callback",
    ]


def test_django_facade_mounts_callback_at_configured_redirect_uri_path() -> None:
    from govbr_auth.django import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(
            ContractClient({"sub": "subject"}),
            redirect_uri=(
                "https://staging.example.test/oauth/govbr/caf%C3%A9%20retorno"
            ),
        ),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    assert [str(pattern.pattern) for pattern in auth.urlpatterns] == [
        "auth/govbr/login",
        "oauth/govbr/café retorno",
    ]
    match = resolve("/oauth/govbr/café retorno", urlconf=tuple(auth.urlpatterns))
    response = match.func(RequestFactory().get("/oauth/govbr/caf%C3%A9%20retorno"))
    assert response.status_code == 400
    with pytest.raises(Resolver404):
        resolve("/auth/govbr/callback", urlconf=tuple(auth.urlpatterns))


def test_django_login_redirects_using_the_core_authorization_url() -> None:
    from govbr_auth.django import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    response = _route(auth, "login")(RequestFactory().get("/auth/govbr/login"))

    assert response.status_code == 302
    assert response["Location"] == "https://sso.example.test/authorize"


def test_django_callback_passes_context_and_request_to_success_handler() -> None:
    from govbr_auth.django import GovBrAuth

    received: list[tuple[object, object]] = []

    def on_success(context, request):
        received.append((context, request))
        return HttpResponse(status=204)

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=on_success,
        clock=lambda: FIXED_NOW,
    )
    request = RequestFactory().get(
        "/auth/govbr/callback",
        {"code": "code", "state": "state"},
    )

    response = _route(auth, "callback")(request)

    assert response.status_code == 204
    assert received[0][1] is request
    assert received[0][0].user.subject == "subject"


def test_django_callback_rejects_missing_oauth_parameters() -> None:
    from govbr_auth.django import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    response = _route(auth, "callback")(RequestFactory().get("/auth/govbr/callback"))

    assert response.status_code == 400


def test_django_fake_runtime_adds_provider_patterns_without_fastapi() -> None:
    from govbr_auth.django import GovBrAuth

    auth = GovBrAuth(
        settings=_fake_runtime_settings(),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    try:
        paths = {str(pattern.pattern) for pattern in auth.urlpatterns}
        assert {
            "auth/govbr/login",
            "auth/govbr/callback",
            "fake-govbr/authorize",
            "fake-govbr/login",
            "fake-govbr/token",
            "fake-govbr/jwk",
            "fake-govbr/userinfo",
        } <= paths
    finally:
        auth.close()


def test_django_fake_runtime_passes_simulator_http_application_to_provider_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import govbr_auth.django as django_adapter
    from govbr_auth.django import GovBrAuth

    mounted: list[tuple[object, object, object]] = []

    def create_patterns(runtime, *, application, clock):
        mounted.append((runtime, application, clock))
        return []

    monkeypatch.setattr(
        django_adapter,
        "create_fake_govbr_urlpatterns",
        create_patterns,
    )

    auth = GovBrAuth(
        settings=_fake_runtime_settings(),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    try:
        runtime = auth._application.runtime.fake
        assert runtime is not None
        assert mounted == [(runtime, runtime.http_application, auth._clock)]
    finally:
        auth.close()


def test_django_rejects_owned_fake_prefix_collision_before_duplicate_post_route() -> (
    None
):
    from govbr_auth.django import GovBrAuth

    settings = GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_provider_prefix="/auth/govbr",
    )
    auth = None
    raised = None

    try:
        try:
            auth = GovBrAuth(
                settings=settings,
                on_success=lambda context, request: HttpResponse(status=204),
                clock=lambda: FIXED_NOW,
            )
        except ValueError as error:
            raised = error

        if auth is not None:
            match = resolve("/auth/govbr/login", urlconf=tuple(auth.urlpatterns))
            response = match.func(RequestFactory().post("/auth/govbr/login"))
            assert (
                response.status_code != 302
            ), "a rota de login do consumidor sombreou o POST do FakeGov"
    finally:
        if auth is not None:
            auth.close()

    assert isinstance(raised, ValueError)
    assert str(raised) == (
        "o prefixo do FakeGov deve ser diferente do prefixo do adapter"
    )


def test_django_rejects_borrowed_fake_prefix_collision() -> None:
    from govbr_auth.adapters._sync import run_sync
    from govbr_auth.django import GovBrAuth

    runtime = _colliding_fake_runtime()

    try:
        with pytest.raises(
            ValueError,
            match="o prefixo do FakeGov deve ser diferente do prefixo do adapter",
        ):
            GovBrAuth(
                runtime=runtime,
                on_success=lambda context, request: HttpResponse(status=204),
                clock=lambda: FIXED_NOW,
            )
    finally:
        run_sync(runtime.aclose)

