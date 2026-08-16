"""Canonical framework-independent composition for the local fake provider."""

from collections.abc import Callable
from dataclasses import dataclass, field
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
from govbr_auth.fake.models import FakeClient, FakeUser
from govbr_auth.fake.provider import FakeGovBrProvider
from govbr_auth.fake.settings import FakeGovBrSettings
from govbr_auth.fake.signing import FakeSigningKey
from govbr_auth.fake.stores import (
    FakeUserStore,
    InMemoryAuthorizationCodeReplayStore,
)
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings


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
class FakeGovBrRuntime:
    """Own one internally consistent fake-provider object graph."""

    settings: FakeGovBrSettings
    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator = field(repr=False)
    users: tuple[FakeUser, ...] = field(repr=False)
    credentials: tuple[FakeLoginCredential, ...] = field(repr=False)
    prefix: str
    endpoints: FakeGovBrEndpoints


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
_DEFAULT_CREDENTIALS = (
    FakeLoginCredential(
        cpf="12345678901",
        password="ana-demo",
        name="Ana Demo",
    ),
    FakeLoginCredential(
        cpf="98765432100",
        password="bruno-demo",
        name="Bruno Demo",
    ),
)


def create_fake_govbr_runtime(
    settings: GovBrRuntimeSettings,
    *,
    clock: Callable[[], datetime],
    user_repository: FakeUserRepository | None = None,
) -> FakeGovBrRuntime:
    """Compose one fake provider without importing an HTTP framework."""
    if settings.provider is not GovBrProvider.FAKE:
        raise ValueError("fake runtime requires the fake provider")

    settings = GovBrRuntimeSettings.model_validate(settings.model_dump())
    del clock
    repository, credentials = _resolve_repository(settings, user_repository)
    prefix = settings.fake_provider_prefix if settings.fake_end_to_end else ""
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
    return FakeGovBrRuntime(
        settings=provider_settings,
        provider=provider,
        credential_authenticator=repository,
        users=repository.list(),
        credentials=credentials,
        prefix=prefix,
        endpoints=endpoints,
    )


def _resolve_repository(
    settings: GovBrRuntimeSettings,
    explicit: FakeUserRepository | None,
) -> tuple[FakeUserRepository, tuple[FakeLoginCredential, ...]]:
    if explicit is not None:
        return explicit, ()
    if settings.fake_users_file is not None:
        return JsonFakeUserRepository.from_file(settings.fake_users_file), ()
    return InMemoryFakeUserRepository(_DEFAULT_USERS), _DEFAULT_CREDENTIALS


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
