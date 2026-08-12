"""Public configuration and storage interfaces for the local Fake Gov.br provider."""

from govbr_auth.fake.models import FakeClient, FakeUser
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.stores import (
    AuthorizationCodeReplayStore,
    FakeUserStore,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
)

__all__ = [
    "AuthorizationCodeReplayStore",
    "FakeClient",
    "FakeGovBrSettings",
    "FakeUser",
    "FakeUserStore",
    "InMemoryAuthorizationCodeReplayStore",
    "InMemoryFakeUserStore",
]
