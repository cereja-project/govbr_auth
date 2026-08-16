"""Public configuration and storage interfaces for the local Fake Gov.br provider."""

from govbr_auth.fake.artifacts import (
    AccessTokenArtifact,
    AuthorizationCodeArtifact,
    AuthorizationRequestArtifact,
    FakeArtifactCodec,
)
from govbr_auth.fake.credentials import (
    FakeCredentialAuthenticator,
    FakeLoginCredential,
    InMemoryFakeUserRepository,
    JsonFakeUserRepository,
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
from govbr_auth.fake.runtime import (
    FakeGovBrEndpoints,
    FakeGovBrRuntime,
    create_fake_govbr_runtime,
)
from govbr_auth.fake.signing import FakeSigningKey, FakeTokenIssuer
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.stores import (
    AuthorizationCodeReplayStore,
    FakeUserStore,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
)

__all__ = (
    "AccessTokenArtifact",
    "AuthorizationCodeArtifact",
    "AuthorizationCodeReplayStore",
    "AuthorizationRequestArtifact",
    "FakeArtifactCodec",
    "FakeAuthorizationRedirect",
    "FakeAuthorizationRequest",
    "FakeAuthorizationSession",
    "FakeClient",
    "FakeClientCredentials",
    "FakeCredentialAuthenticator",
    "FakeGovBrEndpoints",
    "FakeGovBrProvider",
    "FakeGovBrRuntime",
    "FakeGovBrSettings",
    "FakeLoginCredential",
    "FakeOAuthError",
    "FakeSigningKey",
    "FakeTokenIssuer",
    "FakeTokenRequest",
    "FakeTokenResponse",
    "FakeUser",
    "FakeUserStore",
    "InMemoryAuthorizationCodeReplayStore",
    "InMemoryFakeUserStore",
    "InMemoryFakeUserRepository",
    "JsonFakeUserRepository",
    "create_fake_govbr_runtime",
    "create_fake_govbr_app",
    "create_fake_govbr_router",
)


def __getattr__(name: str) -> object:
    """Load optional FastAPI factories only when callers request them."""
    if name not in {"create_fake_govbr_app", "create_fake_govbr_router"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from govbr_auth.fake.fastapi import (
        create_fake_govbr_app,
        create_fake_govbr_router,
    )

    factories = {
        "create_fake_govbr_app": create_fake_govbr_app,
        "create_fake_govbr_router": create_fake_govbr_router,
    }
    value = factories[name]
    globals()[name] = value
    return value
