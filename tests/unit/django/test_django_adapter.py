"""Unit contract for the native Django consumer adapter."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
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
from govbr_auth.runtime import GovBrProvider, GovBrRuntime, GovBrRuntimeSettings

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


def _runtime(client: ContractClient) -> GovBrRuntime:
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL),
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
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
        ),
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
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
        ),
        on_success=lambda context, request: HttpResponse(status=204),
        clock=lambda: FIXED_NOW,
    )

    try:
        runtime = auth._owner.runtime.fake
        assert runtime is not None
        assert mounted == [(runtime, runtime.http_application, auth._clock)]
    finally:
        auth.close()
