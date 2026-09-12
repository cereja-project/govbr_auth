"""Verify browser-proof authenticity, scope, lifetime and cookie policy."""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import pytest
from fastapi.responses import Response
from pydantic import AnyHttpUrl

from govbr_auth.adapters._browser import BrowserBinding
from govbr_auth.core.errors import ExpiredTransactionError, InvalidStateError
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)
STATE = "protected-state"


def oauth_settings(url="http://localhost/auth/govbr/callback"):
    return GovBrRuntimeSettings(provider=GovBrProvider.FAKE).oauth.model_copy(
        update={"redirect_uri": AnyHttpUrl(url)}
    )


def cookie_jar(response):
    jar = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        jar.load(header)
    return jar


def issue(binding, state=STATE, *, now=NOW, pending=None):
    response = Response()
    binding.start(response, state, now=now, cookies=pending or {})
    jar = cookie_jar(response)
    return {name: morsel.value for name, morsel in jar.items()}, response


@pytest.mark.parametrize(
    "url,secure",
    (
        ("https://consumer.example.test/auth/govbr/callback", True),
        ("http://127.0.0.1/auth/govbr/callback", False),
    ),
)
def test_browser_cookie_is_host_only_private_and_separate_from_state(url, secure):
    binding = BrowserBinding(oauth_settings(url))
    cookies, response = issue(binding)
    binding.validate(STATE, cookies, now=NOW)
    name, morsel = next(iter(cookie_jar(response).items()))
    assert name.startswith("__Host-" if secure else "govbr-auth-local-")
    assert bool(morsel["secure"]) is secure
    assert morsel["httponly"]
    assert morsel["path"] == "/"
    assert not morsel["domain"]
    assert morsel["samesite"] == ("none" if secure else "lax")
    assert morsel["max-age"] == "300"
    assert STATE not in name and STATE not in morsel.value
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.parametrize("value", ("", "garbage", "é", STATE))
def test_missing_or_forged_proof_is_rejected_without_disclosing_input(value):
    binding = BrowserBinding(oauth_settings())
    with pytest.raises(InvalidStateError) as caught:
        binding.validate(STATE, {binding.cookie_name(STATE): value}, now=NOW)
    assert str(caught.value) == "OAuth browser binding is invalid"
    assert caught.value.__context__ is None


def test_cookie_cannot_be_renamed_to_authorize_another_state():
    binding = BrowserBinding(oauth_settings())
    cookies, _ = issue(binding)
    proof = cookies[binding.cookie_name(STATE)]
    with pytest.raises(InvalidStateError):
        binding.validate(
            "another-state", {binding.cookie_name("another-state"): proof}, now=NOW
        )


@pytest.mark.parametrize(
    "change",
    (
        {"client_id": "different-client"},
        {"redirect_uri": AnyHttpUrl("http://localhost/other/callback")},
    ),
)
def test_shared_key_does_not_allow_cookie_rebinding_to_another_client(change):
    settings = oauth_settings()
    owner = BrowserBinding(settings)
    other = BrowserBinding(settings.model_copy(update=change))
    cookies, _ = issue(owner)
    proof = cookies[owner.cookie_name(STATE)]
    assert owner.cookie_name(STATE) != other.cookie_name(STATE)
    with pytest.raises(InvalidStateError):
        other.validate(STATE, {other.cookie_name(STATE): proof}, now=NOW)


def test_independent_instances_with_shared_settings_validate_same_proof():
    settings = oauth_settings()
    owner, callback_worker = BrowserBinding(settings), BrowserBinding(settings)
    cookies, _ = issue(owner)
    callback_worker.validate(STATE, cookies, now=NOW + timedelta(seconds=299))


@pytest.mark.parametrize(
    "offset,error",
    (
        (-1, InvalidStateError),
        (300, ExpiredTransactionError),
        (301, ExpiredTransactionError),
    ),
)
def test_proof_lifetime_is_checked_even_when_cookie_jar_retains_it(offset, error):
    binding = BrowserBinding(oauth_settings())
    cookies, _ = issue(binding)
    with pytest.raises(error):
        binding.validate(STATE, cookies, now=NOW + timedelta(seconds=offset))


def test_completion_preserves_session_cookie_and_other_pending_logins():
    binding = BrowserBinding(oauth_settings())
    response = Response()
    response.set_cookie("application-session", "retained", httponly=True)
    binding.finish(response, STATE)
    jar = cookie_jar(response)
    assert set(jar) == {"application-session", binding.cookie_name(STATE)}
    assert jar["application-session"].value == "retained"
    assert jar[binding.cookie_name(STATE)]["max-age"] == "0"
    assert jar[binding.cookie_name(STATE)].value == ""
    binding.finish(Response(), None)


def test_pending_cookie_limit_does_not_delete_another_clients_cookie():
    binding = BrowserBinding(oauth_settings())
    pending = {binding.cookie_name(str(i)): "proof" for i in range(8)}
    pending["application-session"] = "session"
    pending["__Host-other-client"] = "other"
    cookies, response = issue(binding, pending=pending)
    jar = cookie_jar(response)
    assert set(jar) == {binding.cookie_name("0"), binding.cookie_name(STATE)}
    assert jar[binding.cookie_name("0")]["max-age"] == "0"
    assert jar[binding.cookie_name(STATE)]["max-age"] == "300"
    binding.validate(STATE, cookies, now=NOW)
