"""Fail-closed validation for Gov.br OpenID Connect ID tokens."""

import math
import secrets
from collections.abc import Mapping
from datetime import datetime

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from govbr_auth.core.errors import InvalidIdTokenError
from govbr_auth.core.settings import GovBrSettings

_ALLOWED_ALGORITHM = "RS256"
_REQUIRED_CLAIMS = ("exp", "iat", "iss", "aud", "sub", "nonce")


class IdTokenValidator:
    """Validate signed ID tokens against configured identity and JWKS data."""

    def __init__(self, *, settings: GovBrSettings) -> None:
        self._settings = settings

    def validate(
        self,
        id_token: SecretStr,
        expected_nonce: SecretStr,
        *,
        jwks: Mapping[str, object],
        now: datetime,
    ) -> Mapping[str, object]:
        """Return verified claims or raise a stable domain error.

        Args:
            id_token: Compact JWT received from the token endpoint.
            expected_nonce: Nonce bound to the originating authorization transaction.
            jwks: Provider JSON Web Key Set used for this validation call.
            now: Trusted current time used for deterministic temporal validation.

        Returns:
            The verified ID token claims.

        Raises:
            InvalidIdTokenError: If any cryptographic or claim validation fails.
            ValueError: If ``now`` does not carry explicit timezone information.
        """
        self._require_timezone_aware(now)
        raw_token = id_token.get_secret_value()
        try:
            header = jwt.get_unverified_header(raw_token)
            signing_key = self._select_signing_key(header, jwks=jwks)
            claims: dict[str, object] = jwt.decode(
                raw_token,
                key=signing_key.key,
                algorithms=[_ALLOWED_ALGORITHM],
                audience=self._settings.client_id,
                issuer=str(self._settings.issuer),
                options={
                    "require": list(_REQUIRED_CLAIMS),
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "verify_signature": True,
                    "verify_sub": False,
                },
                leeway=self._settings.clock_skew_seconds,
            )
            self._validate_identity_claims(claims)
            self._validate_temporal_claims(claims, now=now)
        except jwt.PyJWTError as error:
            raise InvalidIdTokenError("ID token validation failed") from error

        nonce = claims["nonce"]
        if not isinstance(nonce, str) or not secrets.compare_digest(
            nonce.encode("utf-8"),
            expected_nonce.get_secret_value().encode("utf-8"),
        ):
            raise InvalidIdTokenError(
                "ID token nonce does not match the authorization transaction"
            )
        return claims

    def _validate_identity_claims(self, claims: Mapping[str, object]) -> None:
        audience = claims["aud"]
        expected_audience = self._settings.client_id
        if audience != expected_audience and audience != [expected_audience]:
            raise jwt.InvalidAudienceError(
                "ID token audience is not exclusively bound to the client"
            )

        if "azp" in claims:
            authorized_party = claims["azp"]
            if (
                not isinstance(authorized_party, str)
                or authorized_party != expected_audience
            ):
                raise jwt.InvalidTokenError(
                    "ID token authorized party does not match the client"
                )

        subject = claims["sub"]
        if not isinstance(subject, str) or not subject.strip():
            raise jwt.InvalidTokenError("ID token subject is invalid")

    def _select_signing_key(
        self,
        header: Mapping[str, object],
        *,
        jwks: Mapping[str, object],
    ) -> jwt.PyJWK:
        if header.get("alg") != _ALLOWED_ALGORITHM:
            raise jwt.InvalidAlgorithmError("ID token algorithm is not allowed")

        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise jwt.InvalidTokenError("ID token does not identify a signing key")

        if not isinstance(jwks, Mapping):
            raise jwt.PyJWKSetError("JWKS must be a JSON object")
        keys = jwks.get("keys")
        if not isinstance(keys, list) or not keys:
            raise jwt.PyJWKSetError("JWKS does not contain valid key objects")

        normalized_keys: list[dict[str, object]] = []
        for key in keys:
            if not isinstance(key, Mapping):
                raise jwt.PyJWKSetError("JWKS does not contain valid key objects")
            normalized_keys.append(dict(key))
        return self._parse_signing_key(key_id, normalized_keys)

    def _parse_signing_key(
        self,
        key_id: str,
        keys: list[dict[str, object]],
    ) -> jwt.PyJWK:
        try:
            parsed_keys = tuple(jwt.PyJWK.from_dict(key) for key in keys)
        except (jwt.PyJWTError, TypeError, ValueError) as error:
            raise jwt.PyJWKError("JWKS signing key is malformed") from error

        for key in parsed_keys:
            self._validate_signing_key(key)

        matching_keys = tuple(key for key in parsed_keys if key.key_id == key_id)
        if not matching_keys:
            raise jwt.PyJWKClientError("No matching signing key is available")
        if len(matching_keys) > 1:
            raise jwt.PyJWKSetError("JWKS contains an ambiguous key identifier")
        return matching_keys[0]

    @staticmethod
    def _validate_signing_key(signing_key: jwt.PyJWK) -> None:
        if not isinstance(signing_key.public_key_use, (str, type(None))):
            raise jwt.PyJWKError("JWKS key use is malformed")
        if (
            signing_key.algorithm_name != _ALLOWED_ALGORITHM
            or signing_key.public_key_use not in {None, "sig"}
        ):
            raise jwt.InvalidAlgorithmError(
                "Signing key is not allowed for RS256 signatures"
            )
        if not isinstance(signing_key.key, rsa.RSAPublicKey):
            raise jwt.InvalidKeyError("Signing key is not an RSA public key")

    def _validate_temporal_claims(
        self,
        claims: Mapping[str, object],
        *,
        now: datetime,
    ) -> None:
        expires_at = self._numeric_date(claims["exp"], claim_name="exp")
        issued_at = self._numeric_date(claims["iat"], claim_name="iat")
        timestamp = now.timestamp()
        leeway = self._settings.clock_skew_seconds

        if expires_at <= timestamp - leeway:
            raise jwt.ExpiredSignatureError("ID token has expired")
        if issued_at > timestamp + leeway:
            raise jwt.ImmatureSignatureError("ID token was issued in the future")
        if "nbf" in claims:
            not_before = self._numeric_date(claims["nbf"], claim_name="nbf")
            if not_before > timestamp + leeway:
                raise jwt.ImmatureSignatureError("ID token is not yet valid")

    @staticmethod
    def _numeric_date(value: object, *, claim_name: str) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise jwt.DecodeError(f"ID token {claim_name} claim is not a NumericDate")
        if isinstance(value, float) and not math.isfinite(value):
            raise jwt.DecodeError(
                f"ID token {claim_name} claim is not a finite NumericDate"
            )
        return value

    @staticmethod
    def _require_timezone_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
