"""Tests for the framework-independent Fake Gov.br OAuth provider."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
import jwt
import pytest
from pydantic import SecretStr

from govbr_auth.fake import (
    AccessTokenArtifact,
    AuthorizationCodeArtifact,
    FakeArtifactCodec,
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClient,
    FakeClientCredentials,
    FakeGovBrProvider,
    FakeGovBrSettings,
    FakeOAuthError,
    FakeSigningKey,
    FakeTokenRequest,
    FakeUser,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
VERIFIER = "provider-pkce-verifier-abcdefghijklmnopqrstuvwxyz0123456789"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode("ascii")).digest())
    .rstrip(b"=")
    .decode("ascii")
)


@pytest.fixture
def settings() -> FakeGovBrSettings:
    return FakeGovBrSettings(
        base_url="http://localhost:8000/",
        issuer="http://localhost:8000/",
        artifact_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id="client-123",
                client_secret=SecretStr("client-secret-123"),
                registered_redirect_uris=("https://client.example/callback",),
            ),
        ),
    )


@pytest.fixture
def user() -> FakeUser:
    return FakeUser(
        sub="12345678900",
        name="Maria da Silva",
        email="maria@example.test",
        email_verified=True,
    )


@pytest.fixture
def provider(settings: FakeGovBrSettings, user: FakeUser) -> FakeGovBrProvider:
    return FakeGovBrProvider(
        settings=settings,
        user_store=InMemoryFakeUserStore((user,)),
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=FakeSigningKey.generate(kid="fake-provider-key"),
    )


def _authorization_request(**overrides: str) -> FakeAuthorizationRequest:
    values = {
        "response_type": "code",
        "client_id": "client-123",
        "redirect_uri": "https://client.example/callback",
        "scope": "openid profile email",
        "state": "state-123",
        "nonce": "nonce-123",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    values.update(overrides)
    return FakeAuthorizationRequest(**values)


def _client_credentials(**overrides: object) -> FakeClientCredentials:
    values = {
        "client_id": "client-123",
        "client_secret": SecretStr("client-secret-123"),
    }
    values.update(overrides)
    return FakeClientCredentials(**values)


def _token_request(code: SecretStr, **overrides: object) -> FakeTokenRequest:
    values = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://client.example/callback",
        "code_verifier": SecretStr(VERIFIER),
    }
    values.update(overrides)
    return FakeTokenRequest(**values)


def _authorization_code(
    settings: FakeGovBrSettings,
    *,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(minutes=1),
    client_id: str = "client-123",
    redirect_uri: str = "https://client.example/callback",
    subject: str = "12345678900",
    challenge: str = CHALLENGE,
) -> SecretStr:
    artifact = AuthorizationCodeArtifact(
        jti="authorization-code-123",
        issued_at=issued_at,
        expires_at=expires_at,
        client_id=client_id,
        redirect_uri=redirect_uri,
        nonce="nonce-123",
        scope="openid profile email",
        code_challenge=challenge,
        subject=subject,
    )
    return FakeArtifactCodec(settings.artifact_secret).encode_authorization_code(
        artifact
    )


def _assert_sanitized(error: BaseException, marker: str) -> None:
    pending = [error]
    visited: set[int] = set()

    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        details = f"{current!s} {current!r} {current.args!r} {current.__dict__!r}"

        assert marker not in details

        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


def _tamper(value: SecretStr) -> SecretStr:
    encoded = value.get_secret_value()
    replacement = "A" if encoded[20] != "A" else "B"
    return SecretStr(f"{encoded[:20]}{replacement}{encoded[21:]}")


def test_provider_is_available_from_fake_package() -> None:
    assert FakeGovBrProvider.__module__ == "govbr_auth.fake.provider"


def test_begin_authorization_returns_opaque_session_and_available_users(
    provider: FakeGovBrProvider,
    user: FakeUser,
) -> None:
    result = provider.begin_authorization(_authorization_request(), now=NOW)

    assert result.users == (user,)
    assert isinstance(result.request, SecretStr)
    assert result.request.get_secret_value() != "state-123"


def test_complete_authorization_returns_redirect_with_code_and_original_state(
    provider: FakeGovBrProvider,
) -> None:
    session = provider.begin_authorization(_authorization_request(), now=NOW)

    result = provider.complete_authorization(
        session=session,
        subject="12345678900",
        now=NOW,
    )

    redirect = urlsplit(result.redirect_uri)
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == (
        "https://client.example/callback"
    )
    assert parse_qs(redirect.query) == {
        "code": [result.code.get_secret_value()],
        "state": ["state-123"],
    }


def test_complete_authorization_selects_sole_user_automatically(
    provider: FakeGovBrProvider,
) -> None:
    session = provider.begin_authorization(_authorization_request(), now=NOW)

    result = provider.complete_authorization(session=session, subject=None, now=NOW)

    assert isinstance(result.code, SecretStr)


def test_exchange_code_returns_bound_tokens(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
) -> None:
    code = _authorization_code(settings)

    result = provider.exchange_code(
        credentials=_client_credentials(),
        request=_token_request(code),
        now=NOW,
    )

    claims = jwt.decode(
        result.id_token.get_secret_value(),
        jwt.PyJWK.from_dict(provider.jwks()["keys"][0]).key,
        algorithms=["RS256"],
        audience="client-123",
        issuer="http://localhost:8000/",
        options={"verify_exp": False},
    )
    assert result.token_type == "Bearer"
    assert result.expires_in == 600
    assert result.scope == "openid profile email"
    assert claims["sub"] == "12345678900"
    assert claims["nonce"] == "nonce-123"


def test_jwks_returns_only_public_key_material(provider: FakeGovBrProvider) -> None:
    jwks = provider.jwks()

    assert len(jwks["keys"]) == 1
    assert jwks["keys"][0]["alg"] == "RS256"
    assert {"d", "p", "q", "dp", "dq", "qi"}.isdisjoint(jwks["keys"][0])


def test_userinfo_returns_exact_user_bound_to_access_token(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
    user: FakeUser,
) -> None:
    code = _authorization_code(settings)
    tokens = provider.exchange_code(
        credentials=_client_credentials(),
        request=_token_request(code),
        now=NOW,
    )

    result = provider.userinfo(tokens.access_token, now=NOW)

    assert result == user


@pytest.mark.parametrize(
    "overrides,error",
    [
        pytest.param(
            {"client_id": "unknown-client"}, "unauthorized_client", id="unknown_client"
        ),
        pytest.param(
            {"redirect_uri": "https://evil.example/callback"},
            "invalid_request",
            id="redirect",
        ),
        pytest.param(
            {"response_type": "token"}, "unsupported_response_type", id="response_type"
        ),
        pytest.param({"scope": "profile email"}, "invalid_scope", id="openid_scope"),
        pytest.param({"state": "   "}, "invalid_request", id="blank_state"),
        pytest.param({"nonce": "   "}, "invalid_request", id="blank_nonce"),
        pytest.param(
            {"code_challenge": "   "}, "invalid_request", id="blank_challenge"
        ),
        pytest.param(
            {"code_challenge_method": "plain"}, "invalid_request", id="pkce_method"
        ),
    ],
)
def test_begin_authorization_rejects_invalid_oauth_request(
    provider: FakeGovBrProvider,
    overrides: dict[str, str],
    error: str,
) -> None:
    with pytest.raises(FakeOAuthError) as error_info:
        provider.begin_authorization(_authorization_request(**overrides), now=NOW)

    assert error_info.value.error == error


def test_complete_authorization_rejects_unknown_user(
    provider: FakeGovBrProvider,
) -> None:
    session = provider.begin_authorization(_authorization_request(), now=NOW)

    with pytest.raises(FakeOAuthError) as error_info:
        provider.complete_authorization(
            session=session,
            subject="unknown-subject",
            now=NOW,
        )

    assert error_info.value.error == "access_denied"


def test_begin_authorization_rejects_unicode_redirect_with_sanitized_oauth_error(
    provider: FakeGovBrProvider,
) -> None:
    marker = "https://cliënt.example/callback"

    with pytest.raises(FakeOAuthError) as error_info:
        provider.begin_authorization(
            _authorization_request(redirect_uri=marker),
            now=NOW,
        )

    assert error_info.value.error == "invalid_request"
    _assert_sanitized(error_info.value, marker)


def test_begin_authorization_rejects_unicode_pkce_challenge_with_sanitized_error(
    provider: FakeGovBrProvider,
) -> None:
    marker = "pkce-challenge-ç"

    with pytest.raises(FakeOAuthError) as error_info:
        provider.begin_authorization(
            _authorization_request(code_challenge=marker),
            now=NOW,
        )

    assert error_info.value.error == "invalid_request"
    _assert_sanitized(error_info.value, marker)


def test_exchange_code_rejects_unicode_client_secret_with_sanitized_oauth_error(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
) -> None:
    marker = "client-secret-🔐"

    with pytest.raises(FakeOAuthError) as error_info:
        provider.exchange_code(
            credentials=_client_credentials(client_secret=SecretStr(marker)),
            request=_token_request(_authorization_code(settings)),
            now=NOW,
        )

    assert error_info.value.error == "invalid_client"
    _assert_sanitized(error_info.value, marker)


def test_exchange_code_rejects_unicode_pkce_challenge_with_sanitized_oauth_error(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
) -> None:
    marker = "pkce-challenge-ç"
    code = _authorization_code(settings, challenge=marker)

    with pytest.raises(FakeOAuthError) as error_info:
        provider.exchange_code(
            credentials=_client_credentials(),
            request=_token_request(code),
            now=NOW,
        )

    assert error_info.value.error == "invalid_grant"
    _assert_sanitized(error_info.value, marker)


@pytest.mark.parametrize(
    "credentials,request_factory,error",
    [
        pytest.param(
            _client_credentials(client_id="wrong-client"),
            _token_request,
            "invalid_client",
            id="client_id",
        ),
        pytest.param(
            _client_credentials(client_secret=SecretStr("wrong-secret")),
            _token_request,
            "invalid_client",
            id="client_secret",
        ),
        pytest.param(
            _client_credentials(),
            lambda code: _token_request(code, grant_type="client_credentials"),
            "unsupported_grant_type",
            id="grant",
        ),
        pytest.param(
            _client_credentials(),
            lambda code: _token_request(
                code, redirect_uri="https://evil.example/callback"
            ),
            "invalid_grant",
            id="redirect",
        ),
        pytest.param(
            _client_credentials(),
            lambda code: _token_request(code, code_verifier=SecretStr("   ")),
            "invalid_grant",
            id="blank_verifier",
        ),
        pytest.param(
            _client_credentials(),
            lambda code: _token_request(
                code, code_verifier=SecretStr("wrong-verifier")
            ),
            "invalid_grant",
            id="pkce",
        ),
    ],
)
def test_exchange_code_rejects_invalid_binding(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
    credentials: FakeClientCredentials,
    request_factory: object,
    error: str,
) -> None:
    code = _authorization_code(settings)

    with pytest.raises(FakeOAuthError) as error_info:
        provider.exchange_code(
            credentials=credentials,
            request=request_factory(code),
            now=NOW,
        )

    assert error_info.value.error == error


@pytest.mark.parametrize(
    "code_factory",
    [
        pytest.param(lambda settings: SecretStr("malformed-code"), id="malformed"),
        pytest.param(
            lambda settings: _tamper(_authorization_code(settings)),
            id="tampered",
        ),
        pytest.param(
            lambda settings: _authorization_code(
                settings,
                issued_at=NOW - timedelta(minutes=2),
                expires_at=NOW - timedelta(minutes=1),
            ),
            id="expired",
        ),
        pytest.param(
            lambda settings: _authorization_code(settings, client_id="other-client"),
            id="client_mismatch",
        ),
    ],
)
def test_exchange_code_rejects_invalid_authorization_code(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
    code_factory: object,
) -> None:
    code = code_factory(settings)

    with pytest.raises(FakeOAuthError) as error_info:
        provider.exchange_code(
            credentials=_client_credentials(),
            request=_token_request(code),
            now=NOW,
        )

    assert error_info.value.error == "invalid_grant"


@pytest.mark.parametrize(
    "invalid_request",
    [
        pytest.param(
            lambda code: _token_request(
                code, redirect_uri="https://evil.example/callback"
            ),
            id="redirect",
        ),
        pytest.param(
            lambda code: _token_request(
                code, code_verifier=SecretStr("wrong-verifier")
            ),
            id="pkce",
        ),
    ],
)
def test_failed_code_check_does_not_consume_valid_code(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
    invalid_request: object,
) -> None:
    code = _authorization_code(settings)
    with pytest.raises(FakeOAuthError):
        provider.exchange_code(
            credentials=_client_credentials(),
            request=invalid_request(code),
            now=NOW,
        )

    result = provider.exchange_code(
        credentials=_client_credentials(),
        request=_token_request(code),
        now=NOW,
    )

    assert result.token_type == "Bearer"


def test_invalid_client_does_not_consume_valid_code(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
) -> None:
    code = _authorization_code(settings)
    with pytest.raises(FakeOAuthError):
        provider.exchange_code(
            credentials=_client_credentials(client_secret=SecretStr("wrong-secret")),
            request=_token_request(code),
            now=NOW,
        )

    result = provider.exchange_code(
        credentials=_client_credentials(),
        request=_token_request(code),
        now=NOW,
    )

    assert result.token_type == "Bearer"


def test_exchange_code_rejects_same_instance_replay(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
) -> None:
    code = _authorization_code(settings)
    provider.exchange_code(
        credentials=_client_credentials(),
        request=_token_request(code),
        now=NOW,
    )

    with pytest.raises(FakeOAuthError) as error_info:
        provider.exchange_code(
            credentials=_client_credentials(),
            request=_token_request(code),
            now=NOW,
        )

    assert error_info.value.error == "invalid_grant"


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda settings: SecretStr("malformed-token"), id="malformed"),
        pytest.param(
            lambda settings: _tamper(_access_token(settings)),
            id="tampered",
        ),
        pytest.param(
            lambda settings: _access_token(
                settings,
                issued_at=NOW - timedelta(minutes=20),
                expires_at=NOW - timedelta(minutes=10),
            ),
            id="expired",
        ),
        pytest.param(
            lambda settings: _access_token(settings, client_id="other-client"),
            id="client_mismatch",
        ),
        pytest.param(
            lambda settings: _access_token(settings, subject="unknown-subject"),
            id="unknown_subject",
        ),
    ],
)
def test_userinfo_rejects_invalid_bearer(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
    token_factory: object,
) -> None:
    token = token_factory(settings)

    with pytest.raises(FakeOAuthError) as error_info:
        provider.userinfo(token, now=NOW)

    assert error_info.value.error == "invalid_token"


def _access_token(
    settings: FakeGovBrSettings,
    *,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(minutes=10),
    client_id: str = "client-123",
    subject: str = "12345678900",
) -> SecretStr:
    artifact = AccessTokenArtifact(
        jti="access-token-123",
        issued_at=issued_at,
        expires_at=expires_at,
        client_id=client_id,
        subject=subject,
        scope="openid profile email",
        issuer=str(settings.issuer),
    )
    return FakeArtifactCodec(settings.artifact_secret).encode_access_token(artifact)


@pytest.mark.parametrize(
    "operation,marker",
    [
        pytest.param(
            lambda provider, settings, marker: provider.begin_authorization(
                _authorization_request(state=marker, response_type="token"), now=NOW
            ),
            "sensitive-state-marker",
            id="authorization",
        ),
        pytest.param(
            lambda provider, settings, marker: provider.exchange_code(
                credentials=_client_credentials(client_secret=SecretStr(marker)),
                request=_token_request(_authorization_code(settings)),
                now=NOW,
            ),
            "sensitive-client-secret-marker",
            id="client_secret",
        ),
        pytest.param(
            lambda provider, settings, marker: provider.exchange_code(
                credentials=_client_credentials(),
                request=_token_request(SecretStr(marker)),
                now=NOW,
            ),
            "sensitive-code-marker",
            id="code",
        ),
        pytest.param(
            lambda provider, settings, marker: provider.exchange_code(
                credentials=_client_credentials(),
                request=_token_request(
                    _authorization_code(settings),
                    code_verifier=SecretStr(marker),
                ),
                now=NOW,
            ),
            "sensitive-verifier-marker",
            id="verifier",
        ),
        pytest.param(
            lambda provider, settings, marker: provider.userinfo(
                SecretStr(marker), now=NOW
            ),
            "sensitive-token-marker",
            id="bearer",
        ),
    ],
)
def test_provider_errors_sanitize_sensitive_inputs_and_exception_chains(
    provider: FakeGovBrProvider,
    settings: FakeGovBrSettings,
    operation: object,
    marker: str,
) -> None:
    with pytest.raises(FakeOAuthError) as error_info:
        operation(provider, settings, marker)

    _assert_sanitized(error_info.value, marker)
