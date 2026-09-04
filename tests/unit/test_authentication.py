"""Tests for the framework-neutral authentication application service."""

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.errors import InvalidIdTokenError
from govbr_auth.core.errors import ProviderRejectedError
from govbr_auth.core.models import GovBrUser, TokenSet

FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class StubClient:
    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = dict(claims)
        self.tokens = TokenSet(
            access_token=SecretStr("access-token"),
            id_token=SecretStr("id-token"),
            token_type="Bearer",
            expires_in=300,
            scope="openid profile email",
        )
        self.user = GovBrUser(sub="subject", name="Test user")
        self.validated_states: list[tuple[str, datetime]] = []

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        return AuthorizationRequest("https://sso.example.test/authorize", "state")

    async def exchange_code(
        self, *, code: str, state: str, now: datetime
    ) -> AuthenticationResult:
        return AuthenticationResult(
            tokens=self.tokens,
            id_token_claims=self.claims,
        )

    async def userinfo(
        self,
        access_token: SecretStr,
        *,
        expected_subject: str,
    ) -> GovBrUser:
        return self.user

    def validate_state(self, state: str, *, now: datetime) -> None:
        self.validated_states.append((state, now))

    def logout_url(self) -> str:
        return "https://sso.example.test/logout?post_logout_redirect_uri=encoded"


def test_authorization_url_delegates_to_the_core_client() -> None:
    from govbr_auth.authentication import AuthenticationService

    service = AuthenticationService(StubClient({"sub": "subject"}))

    request = service.authorization_url(now=FIXED_NOW)

    assert request.url == "https://sso.example.test/authorize"
    assert request.state == "state"


@pytest.mark.asyncio
async def test_authenticate_returns_immutable_context_without_tokens_by_default() -> (
    None
):
    from govbr_auth.authentication import AuthenticationService

    claims = {"sub": "subject", "role": "citizen"}
    service = AuthenticationService(StubClient(claims))

    context = await service.authenticate(code="code", state="state", now=FIXED_NOW)

    assert context.user.subject == "subject"
    assert context.claims == claims
    assert isinstance(context.claims, MappingProxyType)
    assert context.tokens is None
    with pytest.raises(TypeError):
        context.claims["role"] = "admin"


@pytest.mark.asyncio
async def test_authenticate_exposes_tokens_only_when_requested() -> None:
    from govbr_auth.authentication import AuthenticationService

    service = AuthenticationService(
        StubClient({"sub": "subject"}),
        expose_tokens=True,
    )

    context = await service.authenticate(code="code", state="state", now=FIXED_NOW)

    assert context.tokens is not None
    assert context.tokens.access_token.get_secret_value() == "access-token"


@pytest.mark.asyncio
async def test_authenticate_rejects_an_id_token_without_a_subject() -> None:
    from govbr_auth.authentication import AuthenticationService

    service = AuthenticationService(StubClient({"sub": ""}))

    with pytest.raises(InvalidIdTokenError, match="usable subject"):
        await service.authenticate(code="code", state="state", now=FIXED_NOW)


def test_provider_error_validates_state_and_discards_provider_description() -> None:
    from govbr_auth.authentication import AuthenticationService

    client = StubClient({"sub": "subject"})
    service = AuthenticationService(client)

    with pytest.raises(ProviderRejectedError) as exc_info:
        service.provider_error(
            error="access_denied",
            state="state",
            error_description="sensitive provider detail",
            now=FIXED_NOW,
        )

    assert client.validated_states == [("state", FIXED_NOW)]
    assert str(exc_info.value) == "Gov.br rejected the authorization request"
    assert "sensitive provider detail" not in str(exc_info.value)


def test_logout_url_delegates_to_the_core_client() -> None:
    from govbr_auth.authentication import AuthenticationService

    assert (
        AuthenticationService(StubClient({"sub": "subject"})).logout_url()
        == "https://sso.example.test/logout?post_logout_redirect_uri=encoded"
    )
