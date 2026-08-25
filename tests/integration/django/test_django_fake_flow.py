"""End-to-end FakeGov authentication through the native Django adapter."""

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from django.conf import settings

if not settings.configured:
    settings.configure(
        ALLOWED_HOSTS=["testserver", "127.0.0.1"],
        DEFAULT_CHARSET="utf-8",
        ROOT_URLCONF=__name__,
        SECRET_KEY="tests-only",
    )

import django

django.setup()

from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import clear_url_caches

from govbr_auth.django import GovBrAuth
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

urlpatterns = []


def _path(location: str) -> str:
    parsed = urlsplit(location)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def test_django_fake_runtime_completes_browser_authentication_flow() -> None:
    received: list[str] = []

    def authenticated(context, request):
        received.append(context.user.subject)
        return JsonResponse({"authenticated": True})

    auth = GovBrAuth(
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
        ),
        on_success=authenticated,
        clock=lambda: datetime(2026, 8, 25, 12, tzinfo=UTC),
    )
    global urlpatterns
    urlpatterns = auth.urlpatterns
    clear_url_caches()

    try:
        with override_settings(ROOT_URLCONF=__name__):
            client = Client()
            login = client.get("/auth/govbr/login")
            authorize = client.get(_path(login["Location"]))
            request_value = re.search(
                r'name="request" value="([^"]+)"', authorize.content.decode()
            ).group(1)
            fake_login = client.post(
                "/fake-govbr/login",
                {
                    "request": request_value,
                    "cpf": "12345678901",
                    "password": "ana-demo",
                },
            )
            callback = client.get(_path(fake_login["Location"]))

        assert login.status_code == 302
        assert authorize.status_code == 200
        assert fake_login.status_code == 302
        assert callback.status_code == 200
        assert callback.json() == {"authenticated": True}
        assert received == ["12345678901"]
    finally:
        auth.close()
        urlpatterns = []
        clear_url_caches()
