"""Public configuration and storage interfaces for the local Fake Gov.br provider."""

from govbr_auth.fake.artifacts import (
    AccessTokenArtifact,
    AuthorizationCodeArtifact,
    AuthorizationRequestArtifact,
    FakeArtifactCodec,
)
from govbr_auth.fake.models import FakeClient, FakeUser
from govbr_auth.fake.provider import (
    FakeAuthorizationRedirect,
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeGovBrProvider,
    FakeOAuthError,
    FakeTokenRequest,
    FakeTokenResponse,
)
from govbr_auth.fake.signing import FakeSigningKey, FakeTokenIssuer
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.stores import (
    AuthorizationCodeReplayStore,
    FakeUserStore,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
)

__all__ = [
    "AccessTokenArtifact",
    "AuthorizationCodeReplayStore",
    "AuthorizationCodeArtifact",
    "AuthorizationRequestArtifact",
    "FakeClient",
    "FakeClientCredentials",
    "FakeArtifactCodec",
    "FakeAuthorizationRedirect",
    "FakeAuthorizationRequest",
    "FakeAuthorizationSession",
    "FakeGovBrSettings",
    "FakeGovBrProvider",
    "FakeOAuthError",
    "FakeSigningKey",
    "FakeTokenIssuer",
    "FakeUser",
    "FakeUserStore",
    "FakeTokenRequest",
    "FakeTokenResponse",
    "InMemoryAuthorizationCodeReplayStore",
    "InMemoryFakeUserStore",
]
