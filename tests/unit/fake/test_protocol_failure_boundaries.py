"""Verify provider rejection at artifact, user lookup, and PKCE boundaries."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from govbr_auth.fake.artifacts import (
    AccessTokenArtifact,
    AuthorizationCodeArtifact,
    FakeArtifactCodec,
)
from govbr_auth.fake.protocol import FakeOAuthProtocolRules, _pkce_challenge
from govbr_auth.fake.provider import (
    FakeClientCredentials,
    FakeOAuthError,
    FakeTokenRequest,
)
from govbr_auth.fake.runtime import create_fake_gov_simulator
from govbr_auth.fake.stores import InMemoryAuthorizationCodeReplayStore
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)
VERIFIER = "protocol-boundary-verifier-abcdefghijklmnopqrstuvwxyz0123456789"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode("ascii")).digest())
    .rstrip(b"=")
    .decode("ascii")
)


@pytest.fixture
def exchange():
    simulator = create_fake_gov_simulator(
        GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        prefix="/fake-govbr",
        clock=lambda: NOW,
    )
    client = simulator.settings.clients[0]
    artifact = AuthorizationCodeArtifact(
        jti="test-code-identifier",
        issued_at=NOW,
        expires_at=NOW + timedelta(seconds=60),
        client_id=client.client_id,
        redirect_uri=client.registered_redirect_uris[0],
        nonce="test-nonce",
        scope="openid profile email",
        code_challenge=CHALLENGE,
        subject="11122233344",
    )
    codec = FakeArtifactCodec(simulator.settings.artifact_secret)
    request = FakeTokenRequest(
        grant_type="authorization_code",
        code=codec.encode_authorization_code(artifact),
        redirect_uri=str(client.registered_redirect_uris[0]),
        code_verifier=SecretStr(VERIFIER),
    )
    credentials = FakeClientCredentials(
        client_id=client.client_id, client_secret=client.client_secret
    )
    return simulator, codec, artifact, request, credentials


def test_combined_token_validation_returns_bound_client(exchange):
    simulator, _, artifact, request, credentials = exchange
    rules = FakeOAuthProtocolRules(
        clients=simulator.settings.clients,
        replay_store=InMemoryAuthorizationCodeReplayStore(),
    )
    result = rules.validate_token_request(
        credentials=credentials, request=request, code=artifact
    )
    assert result == simulator.settings.clients[0]


def test_code_binding_rejects_unwrapped_verifier(exchange):
    simulator, _, artifact, request, credentials = exchange
    malformed = FakeTokenRequest(
        grant_type=request.grant_type,
        code=request.code,
        redirect_uri=request.redirect_uri,
        code_verifier=VERIFIER,
    )
    rules = FakeOAuthProtocolRules(
        clients=simulator.settings.clients,
        replay_store=InMemoryAuthorizationCodeReplayStore(),
    )
    with pytest.raises(FakeOAuthError) as caught:
        rules.validate_token_request(
            credentials=credentials, request=malformed, code=artifact
        )
    assert caught.value.error == "invalid_grant"
    assert VERIFIER not in str(caught.value)


def test_pkce_challenge_rejects_non_ascii_input():
    assert _pkce_challenge("é" * 43) is None
    assert _pkce_challenge(VERIFIER) == CHALLENGE


def test_missing_user_rejects_exchange_without_consuming_the_code(
    exchange, monkeypatch
):
    simulator, _, _, request, credentials = exchange
    with monkeypatch.context() as patch:
        patch.setattr(simulator.credential_authenticator, "get", lambda subject: None)
        with pytest.raises(FakeOAuthError) as caught:
            simulator.provider.exchange_code(
                credentials=credentials, request=request, now=NOW
            )
    assert caught.value.error == "invalid_grant"
    assert request.code.get_secret_value() not in str(caught.value)
    tokens = simulator.provider.exchange_code(
        credentials=credentials, request=request, now=NOW
    )
    assert tokens.token_type == "Bearer"
    assert (
        simulator.provider.userinfo(tokens.access_token, now=NOW).sub == "11122233344"
    )


def test_userinfo_rejects_valid_artifact_for_unregistered_client(exchange):
    simulator, codec, _, _, _ = exchange
    artifact = AccessTokenArtifact(
        jti="unknown-client-token",
        issued_at=NOW,
        expires_at=NOW + timedelta(seconds=60),
        client_id="unregistered-client",
        subject="11122233344",
        scope="openid",
        issuer=str(simulator.settings.issuer),
    )
    token = codec.encode_access_token(artifact)
    with pytest.raises(FakeOAuthError) as caught:
        simulator.provider.userinfo(token, now=NOW)
    assert caught.value.error == "invalid_token"
    assert token.get_secret_value() not in str(caught.value)


def test_exchange_rejects_corrupted_authorization_code(exchange):
    simulator, _, _, request, credentials = exchange
    corrupted = FakeTokenRequest(
        grant_type=request.grant_type,
        code=SecretStr("corrupted-private-code-marker"),
        redirect_uri=request.redirect_uri,
        code_verifier=request.code_verifier,
    )
    with pytest.raises(FakeOAuthError) as caught:
        simulator.provider.exchange_code(
            credentials=credentials, request=corrupted, now=NOW
        )
    assert caught.value.error == "invalid_grant"
    assert "corrupted-private-code-marker" not in str(caught.value)
