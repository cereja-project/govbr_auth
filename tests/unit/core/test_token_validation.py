"""Tests for fail-closed OpenID Connect ID token validation."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from govbr_auth.core.errors import InvalidIdTokenError
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.token_validation import IdTokenValidator

FIXED_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
KNOWN_KEY_ID = "govbr-signing-key"


@pytest.fixture
def settings() -> GovBrSettings:
    return GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="test-client",
        client_secret=SecretStr("test-client-secret"),
        redirect_uri="https://client.example.test/callback",
        transaction_secret=SecretStr("test-transaction-secret"),
        issuer="https://sso.example.test",
        jwks_url="https://sso.example.test/jwk",
        clock_skew_seconds=60,
    )


@pytest.fixture
def expected_nonce() -> SecretStr:
    return SecretStr("nonce-bound-to-authorization-transaction")


@pytest.fixture
def rsa_signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def other_rsa_signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks(rsa_signing_key: rsa.RSAPrivateKey) -> dict[str, object]:
    public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_signing_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    return {"keys": [public_jwk]}


@pytest.fixture
def validator(settings: GovBrSettings, jwks: dict[str, object]) -> IdTokenValidator:
    return IdTokenValidator(settings=settings, jwks=jwks)


@pytest.fixture
def valid_claims(
    settings: GovBrSettings, expected_nonce: SecretStr
) -> dict[str, object]:
    return {
        "iss": str(settings.issuer),
        "aud": settings.client_id,
        "exp": int((FIXED_NOW + timedelta(minutes=5)).timestamp()),
        "iat": int(FIXED_NOW.timestamp()),
        "sub": "12345678900",
        "nonce": expected_nonce.get_secret_value(),
    }


@pytest.fixture
def signed_id_token(
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
) -> SecretStr:
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )
    return SecretStr(encoded)


def test_valid_rs256_token_without_azp_returns_claims(
    validator: IdTokenValidator,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    claims = validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert claims["sub"] == "12345678900"
    assert claims["nonce"] == expected_nonce.get_secret_value()


def test_naive_now_rejects_validation_call(
    validator: IdTokenValidator,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    naive_now = FIXED_NOW.replace(tzinfo=None)

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        validator.validate(signed_id_token, expected_nonce, now=naive_now)


def test_invalid_signature_rejects_id_token_without_leaking_token(
    validator: IdTokenValidator,
    other_rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    encoded = jwt.encode(
        valid_claims,
        other_rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )
    id_token = SecretStr(encoded)

    with pytest.raises(
        InvalidIdTokenError, match="ID token validation failed"
    ) as error:
        validator.validate(id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.InvalidSignatureError)
    assert id_token.get_secret_value() not in str(error.value)


def test_hs256_algorithm_rejects_id_token(
    validator: IdTokenValidator,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    encoded = jwt.encode(
        valid_claims,
        "symmetric-test-key-with-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_none_algorithm_rejects_id_token(
    validator: IdTokenValidator,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    encoded = jwt.encode(
        valid_claims,
        key="",
        algorithm="none",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_missing_kid_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    encoded = jwt.encode(valid_claims, rsa_signing_key, algorithm="RS256")

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_unknown_kid_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": "unknown-signing-key"},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_duplicate_kid_rejects_ambiguous_jwks(
    settings: GovBrSettings,
    rsa_signing_key: rsa.RSAPrivateKey,
    other_rsa_signing_key: rsa.RSAPrivateKey,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    first_public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_signing_key.public_key(),
        as_dict=True,
    )
    first_public_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    second_public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        other_rsa_signing_key.public_key(),
        as_dict=True,
    )
    second_public_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    validator = IdTokenValidator(
        settings=settings,
        jwks={"keys": [first_public_jwk, second_public_jwk]},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.PyJWKSetError)


@pytest.mark.parametrize(
    "jwk_field,jwk_value",
    [
        pytest.param("alg", "RS512", id="wrong_key_algorithm"),
        pytest.param("use", "enc", id="encryption_key"),
    ],
)
def test_non_signing_rs256_jwk_rejects_id_token(
    jwk_field: str,
    jwk_value: str,
    settings: GovBrSettings,
    rsa_signing_key: rsa.RSAPrivateKey,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_signing_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    public_jwk[jwk_field] = jwk_value
    validator = IdTokenValidator(settings=settings, jwks={"keys": [public_jwk]})

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_private_rsa_jwk_rejects_id_token_before_decode(
    settings: GovBrSettings,
    rsa_signing_key: rsa.RSAPrivateKey,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    private_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_signing_key,
        as_dict=True,
    )
    private_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    validator = IdTokenValidator(settings=settings, jwks={"keys": [private_jwk]})

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.InvalidKeyError)


@pytest.mark.parametrize(
    "issuer",
    [
        pytest.param("https://attacker.example.test/", id="different_issuer"),
        pytest.param("https://sso.example.test", id="missing_trailing_slash"),
    ],
)
def test_non_exact_issuer_rejects_id_token(
    issuer: str,
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["iss"] = issuer
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_wrong_audience_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["aud"] = "other-client"
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_singleton_audience_list_returns_claims(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
    settings: GovBrSettings,
) -> None:
    valid_claims["aud"] = [settings.client_id]
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    claims = validator.validate(
        SecretStr(encoded),
        expected_nonce,
        now=FIXED_NOW,
    )

    assert claims["aud"] == [settings.client_id]


def test_additional_audience_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
    settings: GovBrSettings,
) -> None:
    valid_claims["aud"] = [settings.client_id, "attacker-client"]
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_matching_authorized_party_returns_claims(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
    settings: GovBrSettings,
) -> None:
    valid_claims["azp"] = settings.client_id
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    claims = validator.validate(
        SecretStr(encoded),
        expected_nonce,
        now=FIXED_NOW,
    )

    assert claims["azp"] == settings.client_id


@pytest.mark.parametrize(
    "authorized_party",
    [
        pytest.param("attacker-client", id="different_client"),
        pytest.param(["test-client"], id="non_string"),
    ],
)
def test_invalid_authorized_party_rejects_id_token(
    authorized_party: object,
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["azp"] = authorized_party
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param(12345678900, id="non_string"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
    ],
)
def test_invalid_subject_rejects_id_token(
    subject: object,
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["sub"] = subject
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_expired_token_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["exp"] = int((FIXED_NOW - timedelta(seconds=61)).timestamp())
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_future_iat_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["iat"] = int((FIXED_NOW + timedelta(seconds=61)).timestamp())
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_future_nbf_rejects_id_token_using_injected_now(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["nbf"] = int((FIXED_NOW + timedelta(seconds=61)).timestamp())
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_valid_nbf_returns_claims_using_injected_now(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["nbf"] = int((FIXED_NOW - timedelta(seconds=1)).timestamp())
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    claims = validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert claims["nbf"] == valid_claims["nbf"]


@pytest.mark.parametrize(
    "claim_name",
    [
        pytest.param("exp", id="missing_exp"),
        pytest.param("iat", id="missing_iat"),
        pytest.param("iss", id="missing_iss"),
        pytest.param("aud", id="missing_aud"),
        pytest.param("sub", id="missing_sub"),
        pytest.param("nonce", id="missing_nonce"),
    ],
)
def test_missing_required_claim_rejects_id_token(
    claim_name: str,
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims.pop(claim_name)
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


@pytest.mark.parametrize(
    "claim_name",
    [
        pytest.param("exp", id="invalid_exp"),
        pytest.param("iat", id="invalid_iat"),
    ],
)
def test_non_numeric_temporal_claim_rejects_id_token(
    claim_name: str,
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims[claim_name] = "not-a-numeric-date"
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


@pytest.mark.parametrize(
    "temporal_value",
    [
        pytest.param("1768478400", id="numeric_string"),
        pytest.param(True, id="boolean"),
        pytest.param(float("inf"), id="infinity"),
    ],
)
def test_non_json_numeric_date_rejects_id_token(
    temporal_value: object,
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["exp"] = temporal_value
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.DecodeError)


def test_numeric_nonce_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
) -> None:
    valid_claims["nonce"] = 123
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), SecretStr("123"), now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"


def test_unicode_nonce_match_returns_claims(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
) -> None:
    valid_claims["nonce"] = "transação-segura-🔐"
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    claims = validator.validate(
        SecretStr(encoded),
        SecretStr("transação-segura-🔐"),
        now=FIXED_NOW,
    )

    assert claims["nonce"] == "transação-segura-🔐"


def test_unicode_nonce_mismatch_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
) -> None:
    valid_claims["nonce"] = "transação-original-🔐"
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(
            SecretStr(encoded),
            SecretStr("transação-diferente-🔐"),
            now=FIXED_NOW,
        )

    assert error.value.code == "invalid_id_token"


def test_nonce_mismatch_rejects_id_token(
    validator: IdTokenValidator,
    rsa_signing_key: rsa.RSAPrivateKey,
    valid_claims: dict[str, object],
    expected_nonce: SecretStr,
) -> None:
    valid_claims["nonce"] = "nonce-from-another-transaction"
    encoded = jwt.encode(
        valid_claims,
        rsa_signing_key,
        algorithm="RS256",
        headers={"kid": KNOWN_KEY_ID},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(SecretStr(encoded), expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "jwks_payload",
    [
        pytest.param({"keys": []}, id="empty_keys"),
        pytest.param({"keys": [1]}, id="non_mapping_key"),
    ],
)
def test_malformed_jwks_rejects_id_token(
    jwks_payload: dict[str, object],
    settings: GovBrSettings,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    validator = IdTokenValidator(settings=settings, jwks=jwks_payload)

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.PyJWKSetError)


@pytest.mark.parametrize(
    "jwks_payload",
    [
        pytest.param([], id="array"),
        pytest.param(None, id="null"),
        pytest.param("not-a-jwks-object", id="string"),
        pytest.param(42, id="integer"),
    ],
)
def test_non_mapping_jwks_rejects_id_token(
    jwks_payload: object,
    settings: GovBrSettings,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    # Deliberately cross the static boundary to verify hostile JSON input at runtime.
    invalid_jwks = cast(Mapping[str, object], jwks_payload)
    validator = IdTokenValidator(settings=settings, jwks=invalid_jwks)

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.PyJWKSetError)


def test_mixed_jwks_with_malformed_member_rejects_entire_set(
    settings: GovBrSettings,
    rsa_signing_key: rsa.RSAPrivateKey,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_signing_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    malformed_jwk = {
        "alg": "RS256",
        "kid": "malformed-key",
        "kty": "RSA",
        "use": "sig",
    }
    validator = IdTokenValidator(
        settings=settings,
        jwks={"keys": [public_jwk, malformed_jwk]},
    )

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.PyJWKError)


@pytest.mark.parametrize(
    "jwk_field,jwk_value",
    [
        pytest.param("alg", ["RS256"], id="algorithm_list"),
        pytest.param("use", ["sig"], id="use_list"),
        pytest.param("n", 123, id="modulus_integer"),
    ],
)
def test_malformed_jwk_field_rejects_id_token(
    jwk_field: str,
    jwk_value: object,
    settings: GovBrSettings,
    rsa_signing_key: rsa.RSAPrivateKey,
    signed_id_token: SecretStr,
    expected_nonce: SecretStr,
) -> None:
    public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_signing_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"alg": "RS256", "kid": KNOWN_KEY_ID, "use": "sig"})
    public_jwk[jwk_field] = jwk_value
    validator = IdTokenValidator(settings=settings, jwks={"keys": [public_jwk]})

    with pytest.raises(InvalidIdTokenError) as error:
        validator.validate(signed_id_token, expected_nonce, now=FIXED_NOW)

    assert error.value.code == "invalid_id_token"
    assert isinstance(error.value.__cause__, jwt.PyJWKError)
