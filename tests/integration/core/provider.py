"""Minimal ASGI identity provider for core integration tests."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

_KEY_ID = "integration-rsa-key"


@dataclass(frozen=True, slots=True)
class _AuthorizationGrant:
    nonce: str
    code_challenge: str
    redirect_uri: str
    scope: str


class GovBrAsgiProvider:
    """Serve a strict local OAuth provider over an in-process ASGI transport."""

    def __init__(
        self,
        *,
        signing_key: rsa.RSAPrivateKey,
        now: datetime,
        base_url: str = "http://127.0.0.1",
        client_id: str = "integration-client",
        client_secret: str = "integration-client-secret",
    ) -> None:
        """Configure deterministic provider identity and real RSA signing."""
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_url = f"{self.base_url}/authorize"
        self.issuer = f"{self.base_url}/"
        self.redirect_uri = f"{self.base_url}/callback"
        self.access_token = "provider-access-token"
        self._signing_key = signing_key
        self._now = now
        self._grants: dict[str, _AuthorizationGrant] = {}
        self._last_nonce: str | None = None
        self._nonce_override: str | None = None
        self._app = Starlette(
            routes=[
                Route("/token", self._token, methods=["POST"]),
                Route("/jwk", self._jwk, methods=["GET"]),
                Route("/userinfo", self._userinfo, methods=["GET"]),
            ]
        )

    @property
    def last_nonce(self) -> str:
        """Return the nonce observed in the latest authorization request."""
        if self._last_nonce is None:
            raise RuntimeError("no authorization request has been accepted")
        return self._last_nonce

    def authorize(self, authorization_url: str) -> str:
        """Validate an authorization URL and issue a bound one-time code."""
        parsed = urlsplit(authorization_url)
        endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if endpoint != self.authorization_url:
            raise ValueError("authorization endpoint is invalid")

        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        response_type = self._single_query_value(query, "response_type")
        client_id = self._single_query_value(query, "client_id")
        redirect_uri = self._single_query_value(query, "redirect_uri")
        challenge_method = self._single_query_value(query, "code_challenge_method")
        nonce = self._single_query_value(query, "nonce")
        code_challenge = self._single_query_value(query, "code_challenge")
        scope = self._single_query_value(query, "scope")
        self._single_query_value(query, "state")

        if response_type != "code":
            raise ValueError("response_type is invalid")
        if client_id != self.client_id:
            raise ValueError("client_id is invalid")
        if redirect_uri != self.redirect_uri:
            raise ValueError("redirect_uri is invalid")
        if challenge_method != "S256":
            raise ValueError("code_challenge_method is invalid")

        code = secrets.token_urlsafe(32)
        self._grants[code] = _AuthorizationGrant(
            nonce=nonce,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
            scope=scope,
        )
        self._last_nonce = nonce
        return code

    def override_nonce(self, nonce: str) -> None:
        """Replace the nonce emitted in the next ID token."""
        self._nonce_override = nonce

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Dispatch one ASGI request to the local provider application."""
        await self._app(scope, receive, send)

    async def _token(self, request: Request) -> Response:
        authorization = request.headers.get("authorization", "")
        expected_credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("ascii")
        ).decode("ascii")
        if not secrets.compare_digest(authorization, f"Basic {expected_credentials}"):
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        body = (await request.body()).decode("utf-8")
        form = {
            name: values[-1]
            for name, values in parse_qs(body, keep_blank_values=True).items()
        }
        code = form.get("code", "")
        grant = self._grants.get(code)
        if grant is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if form.get("grant_type") != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        if form.get("redirect_uri") != grant.redirect_uri:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

        verifier = form.get("code_verifier", "")
        verifier_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = (
            base64.urlsafe_b64encode(verifier_digest).rstrip(b"=").decode("ascii")
        )
        if not secrets.compare_digest(challenge, grant.code_challenge):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

        self._grants.pop(code)
        nonce = grant.nonce if self._nonce_override is None else self._nonce_override
        claims = {
            "iss": self.issuer,
            "aud": self.client_id,
            "exp": int((self._now + timedelta(minutes=5)).timestamp()),
            "iat": int(self._now.timestamp()),
            "sub": "12345678900",
            "nonce": nonce,
        }
        id_token = jwt.encode(
            claims,
            self._signing_key,
            algorithm="RS256",
            headers={"kid": _KEY_ID},
        )
        return JSONResponse(
            {
                "access_token": self.access_token,
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": grant.scope,
            }
        )

    async def _jwk(self, request: Request) -> Response:
        del request
        public_jwk: dict[str, object] = jwt.algorithms.RSAAlgorithm.to_jwk(
            self._signing_key.public_key(),
            as_dict=True,
        )
        public_jwk.update({"alg": "RS256", "kid": _KEY_ID, "use": "sig"})
        return JSONResponse({"keys": [public_jwk]})

    async def _userinfo(self, request: Request) -> Response:
        authorization = request.headers.get("authorization", "")
        if not secrets.compare_digest(
            authorization,
            f"Bearer {self.access_token}",
        ):
            return JSONResponse({"error": "invalid_token"}, status_code=401)
        return JSONResponse(
            {
                "sub": "12345678900",
                "name": "Integration User",
                "email": "integration@example.test",
                "email_verified": True,
            }
        )

    @staticmethod
    def _single_query_value(query: dict[str, list[str]], name: str) -> str:
        values = query.get(name, [])
        if len(values) != 1 or not values[0]:
            raise ValueError(f"authorization query parameter {name} is invalid")
        return values[0]
