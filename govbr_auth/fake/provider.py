"""Framework-independent OAuth 2.0 and OpenID Connect fake provider."""

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
from govbr_auth.fake.models import FakeUser
from govbr_auth.fake.protocol import (
    FakeOAuthError,
    FakeOAuthProtocolRules,
    FakeOAuthRuleSet,
)
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.signing import FakeSigningKey, FakeTokenIssuer
from govbr_auth.fake.stores import AuthorizationCodeReplayStore, FakeUserStore

_AUTHORIZATION_REQUEST_INVALID = "The authorization request is invalid."
_CODE_INVALID = "The authorization code is invalid or expired."
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
    """Return the opaque authorization request carried by the browser."""

    request: SecretStr


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
        protocol_rules: FakeOAuthRuleSet | None = None,
    ) -> None:
        """Create one provider instance with explicit in-memory collaborators."""
        self._settings = settings
        self._user_store = user_store
        self._signing_key = signing_key
        self._codec = FakeArtifactCodec(settings.artifact_secret)
        self._token_issuer = FakeTokenIssuer(
            signing_key=signing_key,
            issuer=str(settings.issuer),
        )
        self._clients = {client.client_id: client for client in settings.clients}
        self._protocol_rules = (
            protocol_rules
            if protocol_rules is not None
            else FakeOAuthProtocolRules(
                clients=settings.clients,
                replay_store=replay_store,
            )
        )
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
        client = self._protocol_rules.validate_authorization_request(request)

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
        )

    def complete_authorization(
        self,
        *,
        session: FakeAuthorizationSession,
        subject: str,
        now: datetime,
    ) -> FakeAuthorizationRedirect:
        """Complete authorization for one authenticated fake user."""
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
        client = self._protocol_rules.authenticate_token_request(
            credentials=credentials,
            request=request,
        )
        code = self._decode_authorization_code(request.code, now=now)
        self._protocol_rules.validate_authorization_code_binding(
            code=code,
            client=client,
            request=request,
        )
        user = self._user_store.get(code.subject)
        if user is None:
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        self._protocol_rules.consume_authorization_code(code, now=now)

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

    def logout(self, post_logout_redirect_uri: str | None) -> str:
        """Validate a registered post-logout redirect URI for the local provider."""
        registered_uris = self._settings.post_logout_redirect_uris
        if not registered_uris:
            origin = urlsplit(str(self._settings.base_url))
            registered_uris = (urlunsplit((origin.scheme, origin.netloc, "/", "", "")),)
        if post_logout_redirect_uri is None or not any(
            secrets.compare_digest(
                str(registered).encode("utf-8"),
                post_logout_redirect_uri.encode("utf-8"),
            )
            for registered in registered_uris
        ):
            raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)
        return post_logout_redirect_uri

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

    def _select_user(self, subject: str) -> FakeUser:
        user = self._user_store.get(subject)
        if user is None:
            raise _oauth_error("access_denied", _USER_DENIED)
        return user


def _oauth_error(error: str, description: str) -> FakeOAuthError:
    return FakeOAuthError(error=error, description=description)


def _append_query(redirect_uri: str, *, code: str, state: str) -> str:
    parts = urlsplit(redirect_uri)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend((("code", code), ("state", state)))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
