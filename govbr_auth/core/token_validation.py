"""Fail-closed validation for Gov.br OpenID Connect ID tokens."""

import math
import secrets
from collections.abc import Mapping
from datetime import datetime

import jwt
from pydantic import SecretStr

from govbr_auth.core.errors import InvalidIdTokenError
from govbr_auth.core.settings import GovBrSettings

_ALLOWED_ALGORITHM = "RS256"
_REQUIRED_CLAIMS = ("exp", "iat", "iss", "aud", "sub", "nonce")


class IdTokenValidator:
    """Validate signed ID tokens against configured identity and JWKS data."""

    def __init__(self, *, settings: GovBrSettings, jwks: Mapping[str, object]) -> None:
        self._settings = settings
        self._jwks = jwks

    def validate(
        self,
        id_token: SecretStr,
        expected_nonce: SecretStr,
        *,
        now: datetime,
    ) -> Mapping[str, object]:
        """Return verified claims or raise a stable domain error.

        Args:
            id_token: Compact JWT received from the token endpoint.
            expected_nonce: Nonce bound to the originating authorization transaction.
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
            signing_key = self._select_signing_key(header)
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
                    "verify_signature": True,
                },
                leeway=self._settings.clock_skew_seconds,
            )
            self._validate_temporal_claims(claims, now=now)
        except jwt.PyJWTError as error:
            raise InvalidIdTokenError("ID token validation failed") from error

        nonce = claims["nonce"]
        if not isinstance(nonce, str) or not secrets.compare_digest(
            nonce, expected_nonce.get_secret_value()
        ):
            raise InvalidIdTokenError(
                "ID token nonce does not match the authorization transaction"
            )
        return claims

    def _select_signing_key(self, header: Mapping[str, object]) -> jwt.PyJWK:
        if header.get("alg") != _ALLOWED_ALGORITHM:
            raise jwt.InvalidAlgorithmError("ID token algorithm is not allowed")

        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise jwt.InvalidTokenError("ID token does not identify a signing key")

        keys = self._jwks.get("keys")
        if (
            not isinstance(keys, list)
            or not keys
            or any(not isinstance(key, Mapping) for key in keys)
        ):
            raise jwt.PyJWKSetError("JWKS does not contain valid key objects")

        return self._parse_signing_key(key_id)

    def _parse_signing_key(self, key_id: str) -> jwt.PyJWK:
        try:
            key_set = jwt.PyJWKSet.from_dict(dict(self._jwks))
            signing_key = next(
                (key for key in key_set.keys if key.key_id == key_id),
                None,
            )
            if signing_key is None:
                raise jwt.PyJWKClientError("No matching signing key is available")
            if (
                signing_key.algorithm_name != _ALLOWED_ALGORITHM
                or signing_key.public_key_use not in {None, "sig"}
            ):
                raise jwt.InvalidAlgorithmError(
                    "Signing key is not allowed for RS256 signatures"
                )
            return signing_key
        except (TypeError, ValueError) as error:
            raise jwt.PyJWKError("JWKS signing key is malformed") from error

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
