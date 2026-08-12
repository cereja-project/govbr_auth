"""Framework-independent OAuth 2.0 and OpenID Connect fake provider."""

import base64
import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

from govbr_auth.fake.artifacts import (
    AccessTokenArtifact,
    AuthorizationCodeArtifact,
    AuthorizationRequestArtifact,
    FakeArtifactCodec,
)
from govbr_auth.fake.models import FakeClient, FakeUser
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.signing import FakeSigningKey, FakeTokenIssuer
from govbr_auth.fake.stores import AuthorizationCodeReplayStore, FakeUserStore

_AUTHORIZATION_REQUEST_INVALID = "The authorization request is invalid."
_CLIENT_INVALID = "Client authentication failed."
_CODE_INVALID = "The authorization code is invalid or expired."
_GRANT_UNSUPPORTED = "The authorization grant type is not supported."
_RESPONSE_TYPE_UNSUPPORTED = "The authorization response type is not supported."
_SCOPE_INVALID = "The requested scope is invalid."
_TOKEN_INVALID = "The access token is invalid or expired."
_USER_DENIED = "The requested fake user is unavailable."


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeAuthorizationRequest:
    """Carry parsed OAuth authorization query values into the provider."""

    response_type: str
    client_id: str
    redirect_uri: str
    scope: str
    state: str
    nonce: str
    code_challenge: str
    code_challenge_method: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeClientCredentials:
    """Carry client credentials parsed separately from HTTP Basic auth."""

    client_id: str
    client_secret: SecretStr


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeTokenRequest:
    """Carry parsed OAuth token form values into the provider."""

    grant_type: str
    code: SecretStr
    redirect_uri: str
    code_verifier: SecretStr


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeAuthorizationSession:
    """Return an opaque authorization request and selectable fake users."""

    request: SecretStr
    users: tuple[FakeUser, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeAuthorizationRedirect:
    """Return a client redirect carrying the code and original OAuth state."""

    redirect_uri: str
    code: SecretStr


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeTokenResponse:
    """Return the exact successful OAuth token response fields."""

    access_token: SecretStr
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    id_token: SecretStr
    scope: str


class FakeOAuthError(Exception):
    """Describe a stable OAuth error without retaining request values."""

    def __init__(self, *, error: str, description: str) -> None:
        """Create an error from safe provider-owned values only."""
        self.error = error
        self.description = description
        super().__init__(f"{error}: {description}")


class FakeGovBrProvider:
    """Coordinate local OAuth artifacts, users, replay state, and RSA tokens."""

    def __init__(
        self,
        *,
        settings: FakeGovBrSettings,
        user_store: FakeUserStore,
        replay_store: AuthorizationCodeReplayStore,
        signing_key: FakeSigningKey,
        identifier_factory: Callable[[], str] | None = None,
    ) -> None:
        """Create one provider instance with explicit in-memory collaborators."""
        self._settings = settings
        self._user_store = user_store
        self._replay_store = replay_store
        self._signing_key = signing_key
        self._codec = FakeArtifactCodec(settings.artifact_secret)
        self._token_issuer = FakeTokenIssuer(
            signing_key=signing_key,
            issuer=str(settings.issuer),
        )
        self._clients = {client.client_id: client for client in settings.clients}
        self._identifier_factory = identifier_factory or (
            lambda: secrets.token_urlsafe(32)
        )

    def begin_authorization(
        self,
        request: FakeAuthorizationRequest,
        *,
        now: datetime,
    ) -> FakeAuthorizationSession:
        """Validate an authorization query and create an opaque browser session."""
        client = self._clients.get(request.client_id)
        if client is None:
            raise _oauth_error("unauthorized_client", _AUTHORIZATION_REQUEST_INVALID)
        if request.response_type != "code":
            raise _oauth_error("unsupported_response_type", _RESPONSE_TYPE_UNSUPPORTED)
        if not self._is_registered_redirect(client, request.redirect_uri):
            raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)
        if "openid" not in request.scope.split():
            raise _oauth_error("invalid_scope", _SCOPE_INVALID)
        if not all(
            value.strip()
            for value in (request.state, request.nonce, request.code_challenge)
        ):
            raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)
        if request.code_challenge_method != "S256":
            raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)

        artifact = AuthorizationRequestArtifact(
            jti=self._identifier_factory(),
            issued_at=now,
            expires_at=now + timedelta(seconds=self._settings.request_ttl_seconds),
            client_id=client.client_id,
            redirect_uri=request.redirect_uri,
            state=request.state,
            nonce=request.nonce,
            scope=request.scope,
            code_challenge=request.code_challenge,
        )
        return FakeAuthorizationSession(
            request=self._codec.encode_authorization_request(artifact),
            users=self._user_store.list(),
        )

    def complete_authorization(
        self,
        *,
        session: FakeAuthorizationSession,
        subject: str | None,
        now: datetime,
    ) -> FakeAuthorizationRedirect:
        """Select a fake user and redirect the client with a short-lived code."""
        request = self._decode_authorization_request(session.request, now=now)
        user = self._select_user(subject)
        code_artifact = AuthorizationCodeArtifact(
            jti=self._identifier_factory(),
            issued_at=now,
            expires_at=now
            + timedelta(seconds=self._settings.authorization_code_ttl_seconds),
            client_id=request.client_id,
            redirect_uri=request.redirect_uri,
            nonce=request.nonce,
            scope=request.scope,
            code_challenge=request.code_challenge,
            subject=user.sub,
        )
        code = self._codec.encode_authorization_code(code_artifact)
        redirect_uri = _append_query(
            str(request.redirect_uri),
            code=code.get_secret_value(),
            state=request.state,
        )
        return FakeAuthorizationRedirect(redirect_uri=redirect_uri, code=code)

    def exchange_code(
        self,
        *,
        credentials: FakeClientCredentials,
        request: FakeTokenRequest,
        now: datetime,
    ) -> FakeTokenResponse:
        """Validate and consume an authorization code before issuing tokens."""
        client = self._authenticate_client(credentials)
        if request.grant_type != "authorization_code":
            raise _oauth_error("unsupported_grant_type", _GRANT_UNSUPPORTED)
        code = self._decode_authorization_code(request.code, now=now)
        self._validate_code_bindings(
            code=code,
            client=client,
            request=request,
        )
        user = self._user_store.get(code.subject)
        if user is None:
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        if not self._replay_store.consume(
            code.jti,
            expires_at=code.expires_at,
            now=now,
        ):
            raise _oauth_error("invalid_grant", _CODE_INVALID)

        access_token = self._issue_access_token(code=code, now=now)
        id_token = self._token_issuer.issue_id_token(
            subject=user.sub,
            audience=client.client_id,
            nonce=code.nonce,
            issued_at=now,
            expires_at=now + timedelta(seconds=self._settings.id_token_ttl_seconds),
            claims=user.model_dump(exclude={"sub"}, exclude_none=True),
        )
        return FakeTokenResponse(
            access_token=access_token,
            expires_in=self._settings.access_token_ttl_seconds,
            id_token=id_token,
            scope=code.scope,
        )

    def jwks(self) -> Mapping[str, object]:
        """Return the provider's public RS256 JSON Web Key Set."""
        return self._signing_key.jwks()

    def userinfo(self, access_token: SecretStr, *, now: datetime) -> FakeUser:
        """Resolve a valid Bearer access token to its exact bound fake user."""
        token = self._decode_access_token(access_token, now=now)
        if token.issuer != str(self._settings.issuer):
            raise _oauth_error("invalid_token", _TOKEN_INVALID)
        if token.client_id not in self._clients:
            raise _oauth_error("invalid_token", _TOKEN_INVALID)
        user = self._user_store.get(token.subject)
        if user is None:
            raise _oauth_error("invalid_token", _TOKEN_INVALID)
        return user

    def _authenticate_client(self, credentials: FakeClientCredentials) -> FakeClient:
        client = self._clients.get(credentials.client_id)
        if client is None or not isinstance(credentials.client_secret, SecretStr):
            raise _oauth_error("invalid_client", _CLIENT_INVALID)
        if not secrets.compare_digest(
            client.client_secret.get_secret_value(),
            credentials.client_secret.get_secret_value(),
        ):
            raise _oauth_error("invalid_client", _CLIENT_INVALID)
        return client

    def _validate_code_bindings(
        self,
        *,
        code: AuthorizationCodeArtifact,
        client: FakeClient,
        request: FakeTokenRequest,
    ) -> None:
        if code.client_id != client.client_id:
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        if str(code.redirect_uri) != request.redirect_uri:
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        if not isinstance(request.code_verifier, SecretStr):
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        verifier = request.code_verifier.get_secret_value()
        if not verifier.strip():
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        challenge = _pkce_challenge(verifier)
        if challenge is None or not secrets.compare_digest(
            challenge, code.code_challenge
        ):
            raise _oauth_error("invalid_grant", _CODE_INVALID)

    def _issue_access_token(
        self,
        *,
        code: AuthorizationCodeArtifact,
        now: datetime,
    ) -> SecretStr:
        artifact = AccessTokenArtifact(
            jti=self._identifier_factory(),
            issued_at=now,
            expires_at=now + timedelta(seconds=self._settings.access_token_ttl_seconds),
            client_id=code.client_id,
            subject=code.subject,
            scope=code.scope,
            issuer=str(self._settings.issuer),
        )
        return self._codec.encode_access_token(artifact)

    def _decode_authorization_request(
        self,
        value: SecretStr,
        *,
        now: datetime,
    ) -> AuthorizationRequestArtifact:
        try:
            return self._codec.decode_authorization_request(value, now=now)
        except ValueError:
            pass
        raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)

    def _decode_authorization_code(
        self,
        value: SecretStr,
        *,
        now: datetime,
    ) -> AuthorizationCodeArtifact:
        try:
            return self._codec.decode_authorization_code(value, now=now)
        except ValueError:
            pass
        raise _oauth_error("invalid_grant", _CODE_INVALID)

    def _decode_access_token(
        self,
        value: SecretStr,
        *,
        now: datetime,
    ) -> AccessTokenArtifact:
        try:
            return self._codec.decode_access_token(value, now=now)
        except ValueError:
            pass
        raise _oauth_error("invalid_token", _TOKEN_INVALID)

    def _select_user(self, subject: str | None) -> FakeUser:
        if subject is None:
            users = self._user_store.list()
            if len(users) != 1:
                raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)
            return users[0]
        user = self._user_store.get(subject)
        if user is None:
            raise _oauth_error("access_denied", _USER_DENIED)
        return user

    @staticmethod
    def _is_registered_redirect(client: FakeClient, redirect_uri: str) -> bool:
        return any(
            secrets.compare_digest(str(registered), redirect_uri)
            for registered in client.registered_redirect_uris
        )


def _oauth_error(error: str, description: str) -> FakeOAuthError:
    return FakeOAuthError(error=error, description=description)


def _pkce_challenge(verifier: str) -> str | None:
    try:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
    except UnicodeEncodeError:
        return None
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _append_query(redirect_uri: str, *, code: str, state: str) -> str:
    parts = urlsplit(redirect_uri)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend((("code", code), ("state", state)))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
