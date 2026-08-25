"""Provider-side OAuth protocol rule collaborators for Fake Gov.br."""

import base64
import hashlib
import re
import secrets
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from govbr_auth.fake.artifacts import AuthorizationCodeArtifact
from govbr_auth.fake.models import FakeClient
from govbr_auth.fake.stores import AuthorizationCodeReplayStore
from pydantic import SecretStr

_AUTHORIZATION_REQUEST_INVALID = "The authorization request is invalid."
_CLIENT_INVALID = "Client authentication failed."
_CODE_INVALID = "The authorization code is invalid or expired."
_GRANT_UNSUPPORTED = "The authorization grant type is not supported."
_RESPONSE_TYPE_UNSUPPORTED = "The authorization response type is not supported."
_SCOPE_INVALID = "The requested scope is invalid."
_S256_CHALLENGE_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}", flags=re.ASCII)


class FakeOAuthError(Exception):
    """Describe a stable OAuth error without retaining request values."""

    def __init__(self, *, error: str, description: str) -> None:
        """Create an error from safe provider-owned values only."""
        self.error = error
        self.description = description
        super().__init__(f"{error}: {description}")


class FakeAuthorizationRequestValues(Protocol):
    """Describe the authorization values validated by provider rules."""

    response_type: str
    client_id: str
    redirect_uri: str
    scope: str
    state: str
    nonce: str
    code_challenge: str
    code_challenge_method: str


class FakeClientCredentialsValues(Protocol):
    """Describe the token client credentials validated by provider rules."""

    client_id: str
    client_secret: SecretStr


class FakeTokenRequestValues(Protocol):
    """Describe the token form values validated by provider rules."""

    grant_type: str
    redirect_uri: str
    code_verifier: SecretStr


class FakeOAuthRuleSet(Protocol):
    """Narrow provider-side contract for injectable OAuth rules."""

    def validate_authorization_request(
        self,
        request: FakeAuthorizationRequestValues,
    ) -> FakeClient: ...

    def authenticate_token_request(
        self,
        *,
        credentials: FakeClientCredentialsValues,
        request: FakeTokenRequestValues,
    ) -> FakeClient: ...

    def validate_authorization_code_binding(
        self,
        *,
        code: AuthorizationCodeArtifact,
        client: FakeClient,
        request: FakeTokenRequestValues,
    ) -> None: ...

    def consume_authorization_code(
        self,
        code: AuthorizationCodeArtifact,
        *,
        now: datetime,
    ) -> None: ...


class FakeOAuthProtocolRules:
    """Validate OAuth protocol rules apart from token signing and storage."""

    def __init__(
        self,
        *,
        clients: Iterable[FakeClient],
        replay_store: AuthorizationCodeReplayStore,
    ) -> None:
        """Create rule collaborators from configured fake clients and replay store."""
        self._clients = {client.client_id: client for client in clients}
        self._replay_store = replay_store

    def validate_authorization_request(
        self,
        request: FakeAuthorizationRequestValues,
    ) -> FakeClient:
        """Return the registered client for a valid authorization request."""
        client = self._clients.get(request.client_id)
        if client is None:
            raise _oauth_error("unauthorized_client", _AUTHORIZATION_REQUEST_INVALID)
        if request.response_type != "code":
            raise _oauth_error("unsupported_response_type", _RESPONSE_TYPE_UNSUPPORTED)
        if not _is_registered_redirect(client, request.redirect_uri):
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
        if not _is_s256_challenge(request.code_challenge):
            raise _oauth_error("invalid_request", _AUTHORIZATION_REQUEST_INVALID)
        return client

    def authenticate_token_request(
        self,
        *,
        credentials: FakeClientCredentialsValues,
        request: FakeTokenRequestValues,
    ) -> FakeClient:
        """Return the authenticated client for a supported token grant."""
        client = self._authenticate_client(credentials)
        if request.grant_type != "authorization_code":
            raise _oauth_error("unsupported_grant_type", _GRANT_UNSUPPORTED)
        return client

    def validate_token_request(
        self,
        *,
        credentials: FakeClientCredentialsValues,
        request: FakeTokenRequestValues,
        code: AuthorizationCodeArtifact,
    ) -> FakeClient:
        """Return the authenticated client for a valid token exchange."""
        client = self.authenticate_token_request(
            credentials=credentials,
            request=request,
        )
        self.validate_authorization_code_binding(
            code=code,
            client=client,
            request=request,
        )
        return client

    def validate_authorization_code_binding(
        self,
        *,
        code: AuthorizationCodeArtifact,
        client: FakeClient,
        request: FakeTokenRequestValues,
    ) -> None:
        """Validate client, redirect URI, and PKCE bindings on a decoded code."""
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
        if (
            challenge is None
            or not _is_s256_challenge(code.code_challenge)
            or not _constant_time_equal(challenge, code.code_challenge)
        ):
            raise _oauth_error("invalid_grant", _CODE_INVALID)

    def consume_authorization_code(
        self,
        code: AuthorizationCodeArtifact,
        *,
        now: datetime,
    ) -> None:
        """Consume a valid authorization code once."""
        if code.expires_at <= now:
            raise _oauth_error("invalid_grant", _CODE_INVALID)
        if not self._replay_store.consume(
            code.jti,
            expires_at=code.expires_at,
            now=now,
        ):
            raise _oauth_error("invalid_grant", _CODE_INVALID)

    def _authenticate_client(
        self,
        credentials: FakeClientCredentialsValues,
    ) -> FakeClient:
        client = self._clients.get(credentials.client_id)
        if client is None or not isinstance(credentials.client_secret, SecretStr):
            raise _oauth_error("invalid_client", _CLIENT_INVALID)
        if not _constant_time_equal(
            client.client_secret.get_secret_value(),
            credentials.client_secret.get_secret_value(),
        ):
            raise _oauth_error("invalid_client", _CLIENT_INVALID)
        return client


def _oauth_error(error: str, description: str) -> FakeOAuthError:
    return FakeOAuthError(error=error, description=description)


def _is_registered_redirect(client: FakeClient, redirect_uri: str) -> bool:
    return any(
        _constant_time_equal(str(registered), redirect_uri)
        for registered in client.registered_redirect_uris
    )


def _pkce_challenge(verifier: str) -> str | None:
    try:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
    except UnicodeEncodeError:
        return None
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _is_s256_challenge(value: str) -> bool:
    return _S256_CHALLENGE_PATTERN.fullmatch(value) is not None


def _constant_time_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
