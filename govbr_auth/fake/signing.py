"""RSA key publication and OpenID Connect token issuance for the fake provider."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

_ALGORITHM = "RS256"
_KEY_SIZE = 2048
_PROTECTED_VALUES = frozenset(
    {"alg", "aud", "exp", "iat", "iss", "kid", "nonce", "sub", "typ"}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeSigningKey:
    """Hold one private RSA key and publish only its public JWK."""

    kid: str
    _private_key: rsa.RSAPrivateKey

    def __post_init__(self) -> None:
        if not isinstance(self.kid, str) or not self.kid.strip():
            raise ValueError("kid must not be blank")
        if self._private_key.key_size < _KEY_SIZE:
            raise ValueError("RSA key size must be at least 2048 bits")

    @classmethod
    def generate(cls, *, kid: str) -> "FakeSigningKey":
        """Generate a 2048-bit RSA signing key with a stable key identifier."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=_KEY_SIZE,
        )
        return cls(kid=kid, _private_key=private_key)

    def jwks(self) -> Mapping[str, object]:
        """Return a public-only RS256 JSON Web Key Set."""
        public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            self._private_key.public_key(),
            as_dict=True,
        )
        public_jwk.update({"alg": _ALGORITHM, "kid": self.kid, "use": "sig"})
        return {"keys": [public_jwk]}

    def _sign(self, claims: Mapping[str, object]) -> str:
        return jwt.encode(
            dict(claims),
            self._private_key,
            algorithm=_ALGORITHM,
            headers={"kid": self.kid, "typ": "JWT"},
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeTokenIssuer:
    """Issue strict RS256 ID tokens for one fake OpenID Connect issuer."""

    signing_key: FakeSigningKey
    issuer: str

    def __post_init__(self) -> None:
        if not isinstance(self.issuer, str) or not self.issuer.strip():
            raise ValueError("issuer must not be blank")

    def issue_id_token(
        self,
        *,
        subject: str,
        audience: str,
        nonce: str,
        issued_at: datetime,
        expires_at: datetime,
        claims: Mapping[str, object] | None = None,
    ) -> SecretStr:
        """Issue an ID token with immutable security and identity claims."""
        self._require_nonblank(subject, name="subject")
        self._require_nonblank(audience, name="audience")
        self._require_nonblank(nonce, name="nonce")
        self._require_timezone_aware(issued_at, name="issued_at")
        self._require_timezone_aware(expires_at, name="expires_at")
        if expires_at <= issued_at:
            raise ValueError("expires_at must be after issued_at")

        additional_claims = {} if claims is None else dict(claims)
        if _PROTECTED_VALUES.intersection(additional_claims):
            raise ValueError("claims cannot override protected values")
        token_claims = {
            **additional_claims,
            "iss": self.issuer,
            "aud": audience,
            "sub": subject,
            "nonce": nonce,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return SecretStr(self.signing_key._sign(token_claims))

    @staticmethod
    def _require_nonblank(value: str, *, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must not be blank")

    @staticmethod
    def _require_timezone_aware(value: datetime, *, name: str) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(f"{name} must be timezone-aware")
