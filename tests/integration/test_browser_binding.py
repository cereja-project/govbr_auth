"""A callback must belong to the browser that initiated its transaction."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings
from tests.integration.browser_support import browser_application

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


def callback_for(auth, authorization_url):
    values = {
        key: value[0]
        for key, value in parse_qs(urlsplit(authorization_url).query).items()
    }
    result = auth._application.runtime.fake.http_application.authorize(
        values, automatic_subject="11122233344"
    )
    parsed = urlsplit(result.redirect.redirect_uri)
    return parsed.path + "?" + parsed.query


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_other_browser_cannot_complete_or_consume_authorization(framework):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        auth,
        browser,
        received,
    ):
        owner, other = browser(), browser()
        login = owner("/auth/govbr/login")
        callback = callback_for(auth, login.headers["location"])
        rejected = other(callback)
        assert rejected.status_code == 400
        assert rejected.json()["error"] == "invalid_state"
        assert received == []
        completed = owner(callback)
        assert completed.status_code == 200
        assert received == ["11122233344"]


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_foreign_error_callback_is_not_accepted_as_provider_rejection(framework):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        _,
        browser,
        received,
    ):
        owner, other = browser(), browser()
        login = owner("/auth/govbr/login")
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        callback = "/auth/govbr/callback?" + urlencode(
            {"error": "access_denied", "state": state}
        )
        assert other(callback).json()["error"] == "invalid_state"
        assert owner(callback).json()["error"] == "provider_rejected"
        assert owner(callback).json()["error"] == "invalid_state"
        assert received == []


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_parallel_tabs_complete_in_reverse_order_and_delete_only_their_proofs(
    framework,
):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        auth,
        browser,
        received,
    ):
        owner = browser()
        first = callback_for(auth, owner("/auth/govbr/login").headers["location"])
        second = callback_for(auth, owner("/auth/govbr/login").headers["location"])
        assert first != second
        for callback in (second, first):
            completed = owner(callback)
            assert completed.status_code == 200
            assert completed.headers["cache-control"] == "no-store"
            assert completed.headers["pragma"] == "no-cache"
            replay = owner(callback)
            assert replay.status_code == 400
            assert replay.json()["error"] == "invalid_state"
        assert received == ["11122233344"] * 2


@pytest.mark.parametrize("framework", ("fastapi", "django", "flask"))
def test_cookie_for_another_valid_transaction_does_not_authorize_a_callback(framework):
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    with browser_application(framework, settings, clock=lambda: NOW) as (
        auth,
        browser,
        received,
    ):
        owner, other = browser(), browser()
        callback = callback_for(auth, owner("/auth/govbr/login").headers["location"])
        other("/auth/govbr/login")
        rejected = other(callback)
        assert rejected.status_code == 400
        assert rejected.json()["error"] == "invalid_state"
        assert received == []
        assert owner(callback).status_code == 200


@pytest.mark.parametrize("framework", ("django", "flask"))
def test_https_form_post_callback_preserves_browser_binding(framework):
    from pydantic import AnyHttpUrl

    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    settings = settings.model_copy(
        update={
            "oauth": settings.oauth.model_copy(
                update={
                    "redirect_uri": AnyHttpUrl(
                        "https://consumer.example.test/auth/govbr/callback"
                    )
                }
            )
        }
    )
    with browser_application(framework, settings, clock=lambda: NOW) as (
        auth,
        browser,
        received,
    ):
        owner = browser()
        login = owner("/auth/govbr/login")
        cookie = login.headers["set-cookie"].lower()
        assert cookie.startswith("__host-")
        assert "secure" in cookie and "httponly" in cookie and "samesite=none" in cookie
        assert "domain=" not in cookie
        callback = urlsplit(callback_for(auth, login.headers["location"]))
        form = {key: value[0] for key, value in parse_qs(callback.query).items()}
        response = owner(callback.path, method="POST", data=form)
        assert response.status_code == 200
        assert received == ["11122233344"]
