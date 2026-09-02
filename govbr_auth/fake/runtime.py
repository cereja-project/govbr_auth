"""Canonical framework-independent composition for the local fake provider."""

from collections.abc import Callable
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from typing import Protocol

from cryptography.fernet import Fernet
from pydantic import SecretStr

from govbr_auth.fake.credentials import (
    FakeCredentialAuthenticator,
    FakeLoginCredential,
    InMemoryFakeUserRepository,
    JsonFakeUserRepository,
)
from govbr_auth.fake.http.application import FakeGovHttpApplication
from govbr_auth.fake.models import FakeClient, FakeUser
from govbr_auth.fake.provider import FakeGovBrProvider
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.signing import FakeSigningKey
from govbr_auth.fake.stores import (
    FakeUserStore,
    InMemoryAuthorizationCodeReplayStore,
)
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings
from govbr_auth.runtime_settings import _is_canonical_path_prefix


class FakeUserRepository(
    FakeCredentialAuthenticator,
    FakeUserStore,
    Protocol,
):
    """Combine the provider's user lookup and login contracts."""


@dataclass(frozen=True, slots=True)
class FakeGovBrEndpoints:
    """Expose the complete endpoint set served by one fake provider."""

    authorize: str
    token: str
    userinfo: str
    jwks: str
    issuer: str


@dataclass(frozen=True, slots=True)
class FakeGovSimulator:
    """Own one internally consistent fake-provider simulation graph."""

    settings: FakeGovBrSettings
    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator = field(repr=False)
    users: tuple[FakeUser, ...] = field(repr=False)
    credentials: tuple[FakeLoginCredential, ...] = field(repr=False)
    prefix: str
    endpoints: FakeGovBrEndpoints
    clock: InitVar[Callable[[], datetime]] = field(repr=False)
    http_application: FakeGovHttpApplication = field(init=False, repr=False)

    def __post_init__(self, clock: Callable[[], datetime]) -> None:
        object.__setattr__(
            self,
            "http_application",
            FakeGovHttpApplication(self, clock=clock),
        )


_DEFAULT_USERS = (
    (
        FakeUser(
            sub="12345678901",
            name="Ana Demo",
            email="ana@example.test",
            email_verified=True,
        ),
        SecretStr("ana-demo"),
    ),
    (
        FakeUser(
            sub="98765432100",
            name="Bruno Demo",
            email="bruno@example.test",
            email_verified=True,
        ),
        SecretStr("bruno-demo"),
    ),
)


def create_fake_gov_simulator(
    settings: GovBrRuntimeSettings,
    *,
    prefix: str,
    clock: Callable[[], datetime],
    user_repository: FakeUserRepository | None = None,
) -> FakeGovSimulator:
    """Compose one fake provider without importing an HTTP framework."""
    if settings.provider is not GovBrProvider.FAKE:
        raise ValueError("fake simulator requires the fake provider")
    if not _is_canonical_path_prefix(prefix, allow_empty=True):
        raise ValueError("prefix must be an empty string or a canonical path")

    settings = GovBrRuntimeSettings.model_validate(settings.model_dump())
    repository, credentials = _resolve_repository(settings, user_repository)
    endpoints = _fake_endpoints(settings, prefix=prefix)
    redirect_uri = settings.fake_redirect_uri or _default_redirect_uri(settings)
    provider_settings = FakeGovBrSettings(
        base_url=endpoints.issuer,
        issuer=endpoints.issuer,
        artifact_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        request_ttl_seconds=settings.fake_request_ttl_seconds,
        authorization_code_ttl_seconds=settings.fake_authorization_code_ttl_seconds,
        access_token_ttl_seconds=settings.fake_access_token_ttl_seconds,
        id_token_ttl_seconds=settings.fake_id_token_ttl_seconds,
        clients=(
            FakeClient(
                client_id=settings.fake_client_id,
                client_secret=settings.fake_client_secret,
                registered_redirect_uris=(redirect_uri,),
            ),
        ),
    )
    provider = FakeGovBrProvider(
        settings=provider_settings,
        user_store=repository,
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=FakeSigningKey.generate(kid="govbr-auth-local-key"),
    )
    return FakeGovSimulator(
        settings=provider_settings,
        provider=provider,
        credential_authenticator=repository,
        users=repository.list(),
        credentials=credentials,
        prefix=prefix,
        endpoints=endpoints,
        clock=clock,
    )


def _resolve_repository(
    settings: GovBrRuntimeSettings,
    explicit: FakeUserRepository | None,
) -> tuple[FakeUserRepository, tuple[FakeLoginCredential, ...]]:
    if explicit is not None:
        return explicit, ()
    if settings.fake_users_file is not None:
        return JsonFakeUserRepository.from_file(settings.fake_users_file), ()
    credentials = tuple(
        FakeLoginCredential(
            cpf=user.sub,
            password=password.get_secret_value(),
            name=user.name,
        )
        for user, password in _DEFAULT_USERS
    )
    return InMemoryFakeUserRepository(_DEFAULT_USERS), credentials


def _fake_endpoints(
    settings: GovBrRuntimeSettings,
    *,
    prefix: str,
) -> FakeGovBrEndpoints:
    base_url = f"{_fake_origin(settings)}{prefix}"
    issuer = f"{base_url}/"
    return FakeGovBrEndpoints(
        authorize=f"{base_url}/authorize",
        token=f"{base_url}/token",
        userinfo=f"{base_url}/userinfo",
        jwks=f"{base_url}/jwk",
        issuer=issuer,
    )


def _fake_origin(settings: GovBrRuntimeSettings) -> str:
    host = settings.fake_host
    rendered_host = f"[{host}]" if host == "::1" else host
    return f"http://{rendered_host}:{settings.fake_port}"


def _default_redirect_uri(settings: GovBrRuntimeSettings) -> str:
    return f"{_fake_origin(settings)}/auth/govbr/callback"
