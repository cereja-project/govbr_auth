"""Tests for the framework-neutral FakeGov HTTP application service."""

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from govbr_auth.fake.models import FakeUser
from govbr_auth.fake.provider import (
    FakeAuthorizationRedirect,
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeOAuthError,
    FakeTokenRequest,
    FakeTokenResponse,
)

FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class ProviderStub:
    def __init__(self) -> None:
        self.user = FakeUser(sub="12345678900", name="Fake user", email="fake@test")
        self.session = FakeAuthorizationSession(
            request=SecretStr("opaque-request"),
        )

    def begin_authorization(
        self, request: FakeAuthorizationRequest, *, now: datetime
    ) -> FakeAuthorizationSession:
        return self.session

    def complete_authorization(
        self,
        *,
        session: FakeAuthorizationSession,
        subject: str,
        now: datetime,
    ) -> FakeAuthorizationRedirect:
        return FakeAuthorizationRedirect(
            redirect_uri="http://consumer.test/callback?code=code&state=state",
            code=SecretStr("code"),
        )

    def exchange_code(
        self,
        *,
        credentials: FakeClientCredentials,
        request: FakeTokenRequest,
        now: datetime,
    ) -> FakeTokenResponse:
        return FakeTokenResponse(
            access_token=SecretStr("access-token"),
            expires_in=300,
            id_token=SecretStr("id-token"),
            scope="openid profile email",
        )

    def jwks(self) -> dict[str, object]:
        return {"keys": []}

    def userinfo(self, access_token: SecretStr, *, now: datetime) -> FakeUser:
        return self.user

    def logout(self, post_logout_redirect_uri: str | None) -> str:
        if post_logout_redirect_uri != "http://consumer.test/signed-out":
            raise FakeOAuthError(error="invalid_request", description="invalid logout")
        return post_logout_redirect_uri


class CredentialStub:
    def authenticate(self, *, cpf: str, password: SecretStr) -> FakeUser:
        return FakeUser(sub="12345678900", name="Fake user", email="fake@test")


class RuntimeStub:
    provider = ProviderStub()
    credential_authenticator = None
    prefix = "/fake-govbr"


def _authorization_values() -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": "client",
        "redirect_uri": "http://consumer.test/callback",
        "scope": "openid profile email",
        "state": "state",
        "nonce": "nonce",
        "code_challenge": "challenge",
        "code_challenge_method": "S256",
    }


def test_authorize_returns_a_session_for_framework_renderers() -> None:
    from govbr_auth.fake.http.application import FakeGovHttpApplication

    application = FakeGovHttpApplication(RuntimeStub(), clock=lambda: FIXED_NOW)

    result = application.authorize(_authorization_values())

    assert result.session.request.get_secret_value() == "opaque-request"
    assert result.redirect is None


def test_token_and_userinfo_delegate_to_the_provider() -> None:
    from govbr_auth.fake.http.application import FakeGovHttpApplication

    application = FakeGovHttpApplication(RuntimeStub(), clock=lambda: FIXED_NOW)
    credentials = FakeClientCredentials(
        client_id="client",
        client_secret=SecretStr("secret"),
    )
    form = {
        "grant_type": "authorization_code",
        "code": "code",
        "redirect_uri": "http://consumer.test/callback",
        "code_verifier": "verifier",
    }

    response = application.token(credentials, form)
    user = application.userinfo("Bearer access-token")

    assert response.access_token.get_secret_value() == "access-token"
    assert user.sub == "12345678900"


def test_missing_authorization_fields_fail_as_oauth_errors() -> None:
    from govbr_auth.fake.http.application import FakeGovHttpApplication

    application = FakeGovHttpApplication(RuntimeStub(), clock=lambda: FIXED_NOW)

    with pytest.raises(FakeOAuthError) as error:
        application.authorize({})

    assert error.value.error == "invalid_request"


def test_logout_delegates_to_the_provider() -> None:
    from govbr_auth.fake.http.application import FakeGovHttpApplication

    application = FakeGovHttpApplication(RuntimeStub(), clock=lambda: FIXED_NOW)

    assert (
        application.logout("http://consumer.test/signed-out")
        == "http://consumer.test/signed-out"
    )
