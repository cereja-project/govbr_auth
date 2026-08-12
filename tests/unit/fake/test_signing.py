"""Tests for RSA signing and public JWKS publication by the fake provider."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.fake.signing import FakeSigningKey, FakeTokenIssuer

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def signing_key() -> FakeSigningKey:
    return FakeSigningKey.generate(kid="fake-rsa-key")


@pytest.fixture
def issuer(signing_key: FakeSigningKey) -> FakeTokenIssuer:
    return FakeTokenIssuer(
        signing_key=signing_key,
        issuer="https://fake-govbr.example.test/",
    )


@pytest.fixture
def validator_settings() -> GovBrSettings:
    return GovBrSettings(
        authorization_url="https://fake-govbr.example.test/authorize",
        token_url="https://fake-govbr.example.test/token",
        userinfo_url="https://fake-govbr.example.test/userinfo",
        client_id="fake-client",
        client_secret=SecretStr("fake-client-secret"),
        redirect_uri="https://consumer.example.test/callback",
        transaction_secret=SecretStr("fake-transaction-secret"),
        issuer="https://fake-govbr.example.test/",
        jwks_url="https://fake-govbr.example.test/jwk",
    )


def test_generate_publishes_stable_public_rs256_jwks() -> None:
    signing_key = FakeSigningKey.generate(kid="fake-rsa-key")

    first_jwks = signing_key.jwks()
    second_jwks = signing_key.jwks()

    assert first_jwks == second_jwks
    assert isinstance(first_jwks["keys"], list)
    assert len(first_jwks["keys"]) == 1
    public_jwk = first_jwks["keys"][0]
    assert public_jwk["kid"] == "fake-rsa-key"
    assert public_jwk["kty"] == "RSA"
    assert public_jwk["use"] == "sig"
    assert public_jwk["alg"] == "RS256"
    assert {"d", "p", "q", "dp", "dq", "qi"}.isdisjoint(public_jwk)
    parsed_key = jwt.PyJWK.from_dict(public_jwk)
    assert isinstance(parsed_key.key, rsa.RSAPublicKey)
    assert parsed_key.key.key_size >= 2048


@pytest.mark.parametrize(
    "kid",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
    ],
)
def test_generate_rejects_blank_key_identifier(kid: str) -> None:
    with pytest.raises(ValueError, match="kid must not be blank"):
        FakeSigningKey.generate(kid=kid)


def test_signing_key_rejects_blank_key_identifier_when_constructed() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(ValueError, match="kid must not be blank"):
        FakeSigningKey(kid="   ", _private_key=private_key)


def test_signing_key_rejects_rsa_key_smaller_than_2048_bits() -> None:
    weak_private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)

    with pytest.raises(ValueError, match="RSA key size must be at least 2048 bits"):
        FakeSigningKey(kid="weak-rsa-key", _private_key=weak_private_key)


def test_issue_id_token_is_accepted_by_real_validator(
    issuer: FakeTokenIssuer,
    signing_key: FakeSigningKey,
    validator_settings: GovBrSettings,
) -> None:
    token = issuer.issue_id_token(
        subject="12345678900",
        audience="fake-client",
        nonce="authorization-nonce",
        issued_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=5),
        claims={"email_verified": True},
    )
    validator = IdTokenValidator(settings=validator_settings)

    decoded = validator.validate(
        token,
        SecretStr("authorization-nonce"),
        jwks=signing_key.jwks(),
        now=FIXED_NOW,
    )

    assert decoded == {
        "iss": "https://fake-govbr.example.test/",
        "aud": "fake-client",
        "sub": "12345678900",
        "nonce": "authorization-nonce",
        "iat": int(FIXED_NOW.timestamp()),
        "exp": int((FIXED_NOW + timedelta(minutes=5)).timestamp()),
        "email_verified": True,
    }


def test_issue_id_token_uses_only_protected_rs256_header(
    issuer: FakeTokenIssuer,
) -> None:
    token = issuer.issue_id_token(
        subject="12345678900",
        audience="fake-client",
        nonce="authorization-nonce",
        issued_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=5),
    )

    header = jwt.get_unverified_header(token.get_secret_value())

    assert header == {"alg": "RS256", "kid": "fake-rsa-key", "typ": "JWT"}


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("subject", "", id="empty_subject"),
        pytest.param("subject", "   ", id="whitespace_subject"),
        pytest.param("audience", "", id="empty_audience"),
        pytest.param("audience", "   ", id="whitespace_audience"),
        pytest.param("nonce", "", id="empty_nonce"),
        pytest.param("nonce", "   ", id="whitespace_nonce"),
    ],
)
def test_issue_id_token_rejects_blank_security_binding(
    issuer: FakeTokenIssuer,
    field: str,
    value: str,
) -> None:
    arguments = {
        "subject": "12345678900",
        "audience": "fake-client",
        "nonce": "authorization-nonce",
        "issued_at": FIXED_NOW,
        "expires_at": FIXED_NOW + timedelta(minutes=5),
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=f"{field} must not be blank"):
        issuer.issue_id_token(**arguments)


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("issued_at", id="issued_at"),
        pytest.param("expires_at", id="expires_at"),
    ],
)
def test_issue_id_token_rejects_naive_timestamps(
    issuer: FakeTokenIssuer,
    field: str,
) -> None:
    arguments = {
        "subject": "12345678900",
        "audience": "fake-client",
        "nonce": "authorization-nonce",
        "issued_at": FIXED_NOW,
        "expires_at": FIXED_NOW + timedelta(minutes=5),
    }
    arguments[field] = FIXED_NOW.replace(tzinfo=None)

    with pytest.raises(ValueError, match=f"{field} must be timezone-aware"):
        issuer.issue_id_token(**arguments)


def test_issue_id_token_rejects_non_positive_validity_window(
    issuer: FakeTokenIssuer,
) -> None:
    with pytest.raises(ValueError, match="expires_at must be after issued_at"):
        issuer.issue_id_token(
            subject="12345678900",
            audience="fake-client",
            nonce="authorization-nonce",
            issued_at=FIXED_NOW,
            expires_at=FIXED_NOW,
        )


@pytest.mark.parametrize(
    "protected_name",
    [
        pytest.param("iss", id="issuer"),
        pytest.param("aud", id="audience"),
        pytest.param("sub", id="subject"),
        pytest.param("nonce", id="nonce"),
        pytest.param("iat", id="issued_at"),
        pytest.param("exp", id="expires_at"),
        pytest.param("alg", id="algorithm_header"),
        pytest.param("kid", id="key_id_header"),
        pytest.param("typ", id="type_header"),
    ],
)
def test_issue_id_token_rejects_caller_override_of_protected_values(
    issuer: FakeTokenIssuer,
    protected_name: str,
) -> None:
    with pytest.raises(ValueError, match="claims cannot override protected values"):
        issuer.issue_id_token(
            subject="12345678900",
            audience="fake-client",
            nonce="authorization-nonce",
            issued_at=FIXED_NOW,
            expires_at=FIXED_NOW + timedelta(minutes=5),
            claims={protected_name: "attacker-controlled"},
        )
