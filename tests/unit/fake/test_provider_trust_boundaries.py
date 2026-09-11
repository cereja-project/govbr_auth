"""Keep local provider artifacts bound to the intended issuer and runtime."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from govbr_auth.fake.artifacts import AccessTokenArtifact, FakeArtifactCodec
from govbr_auth.fake.provider import FakeAuthorizationSession, FakeOAuthError
from govbr_auth.fake.runtime import create_fake_gov_simulator
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


@pytest.fixture
def simulator():
    return create_fake_gov_simulator(
        GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        prefix="/fake-govbr",
        clock=lambda: NOW,
    )


def test_userinfo_rejects_authentic_artifact_bound_to_another_issuer(simulator):
    codec = FakeArtifactCodec(simulator.settings.artifact_secret)
    artifact = AccessTokenArtifact(
        jti="foreign-issuer-token",
        issued_at=NOW,
        expires_at=NOW + timedelta(seconds=60),
        client_id=simulator.settings.clients[0].client_id,
        subject="11122233344",
        scope="openid",
        issuer="https://different-provider.example.test/",
    )
    token = codec.encode_access_token(artifact)
    with pytest.raises(FakeOAuthError) as caught:
        simulator.provider.userinfo(token, now=NOW)
    assert caught.value.error == "invalid_token"
    assert token.get_secret_value() not in str(caught.value)
    assert artifact.issuer not in str(caught.value)


def test_authorization_rejects_corrupted_session_before_issuing_a_code(simulator):
    session = FakeAuthorizationSession(
        request=SecretStr("corrupted-private-session-marker")
    )
    with pytest.raises(FakeOAuthError) as caught:
        simulator.provider.complete_authorization(
            session=session, subject="11122233344", now=NOW
        )
    assert caught.value.error == "invalid_request"
    assert "corrupted-private-session-marker" not in str(caught.value)


def test_simulator_rejects_official_provider_selection_before_composition():
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE).model_copy(
        update={"provider": GovBrProvider.OFFICIAL}
    )
    with pytest.raises(ValueError, match="requires the fake provider"):
        create_fake_gov_simulator(settings, prefix="/fake-govbr", clock=lambda: NOW)
