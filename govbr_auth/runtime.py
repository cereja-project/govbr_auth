"""Framework-neutral configuration and composition for Gov.br runtimes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import TYPE_CHECKING, Callable
import httpx

from pydantic import SecretStr

from govbr_auth.core.client import GovBrClient
from govbr_auth.core.settings import GovBrSettings, ProviderEnvironment
from govbr_auth.runtime_settings import (
    GovBrProvider,
    GovBrRuntimeSettings,
)
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import (
    EncryptedTransactionCodec,
    generate_transaction_secret,
)

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeGovSimulator, FakeUserRepository


@dataclass(slots=True)
class GovBrRuntime:
    """Own the client resources created by the framework-neutral runtime."""

    settings: GovBrRuntimeSettings
    client: GovBrClient
    provider: GovBrProvider
    fake: "FakeGovSimulator | None"
    _owned_http: httpx.AsyncClient | None
    _closed: bool = False

    @property
    def is_closed(self) -> bool:
        """Return whether this runtime has already completed its lifecycle."""
        return self._closed

    async def __aenter__(self) -> "GovBrRuntime":
        """Enter the runtime lifecycle context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close resources when leaving the runtime lifecycle context."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client created by this runtime exactly once."""
        if not self._closed and self._owned_http is not None:
            await self._owned_http.aclose()
        self._closed = True


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time for runtime collaborators."""
    return datetime.now(UTC)


def create_govbr_runtime(
    settings: GovBrRuntimeSettings,
    *,
    http: httpx.AsyncClient | None = None,
    fake_transport_factory: (
        Callable[["FakeGovSimulator"], httpx.AsyncBaseTransport] | None
    ) = None,
    clock: Callable[[], datetime] = utc_now,
    user_repository: "FakeUserRepository | None" = None,
) -> GovBrRuntime:
    """Compose an official or local fake runtime without a web framework."""
    if settings.provider is GovBrProvider.FAKE:
        return _create_fake_consumer_runtime(
            settings,
            http=http,
            fake_transport_factory=fake_transport_factory,
            clock=clock,
            user_repository=user_repository,
        )

    oauth = settings.oauth
    if oauth is None:
        raise ValueError("official runtime requires OAuth settings")

    create_client = _create_client(oauth)
    owned_http = None if http is not None else httpx.AsyncClient()
    client = create_client(http if http is not None else owned_http)
    return GovBrRuntime(
        settings=settings,
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=owned_http,
    )


def _create_fake_consumer_runtime(
    settings: GovBrRuntimeSettings,
    *,
    http: httpx.AsyncClient | None,
    fake_transport_factory: (
        Callable[["FakeGovSimulator"], httpx.AsyncBaseTransport] | None
    ),
    clock: Callable[[], datetime],
    user_repository: "FakeUserRepository | None",
) -> GovBrRuntime:
    """Compose the fake provider before allocating its owned HTTP client."""
    if http is not None:
        raise ValueError("fake runtime does not accept an HTTP client")
    if fake_transport_factory is None:
        raise ValueError("fake transport factory is required")

    from govbr_auth.fake.runtime import create_fake_gov_simulator

    fake = create_fake_gov_simulator(
        settings,
        prefix=settings.fake_provider_prefix,
        clock=clock,
        user_repository=user_repository,
    )
    oauth = _fake_oauth_settings(fake)
    create_client = _create_client(oauth)
    transport = fake_transport_factory(fake)
    if not isinstance(transport, httpx.AsyncBaseTransport):
        raise TypeError("fake transport factory must return AsyncBaseTransport")
    owned_http = httpx.AsyncClient(transport=transport)
    return GovBrRuntime(
        settings=settings,
        client=create_client(owned_http),
        provider=GovBrProvider.FAKE,
        fake=fake,
        _owned_http=owned_http,
    )


def _fake_oauth_settings(fake: "FakeGovSimulator") -> GovBrSettings:
    """Derive consumer settings from the validated fake-provider graph."""
    client = fake.settings.clients[0]
    return GovBrSettings(
        environment=ProviderEnvironment.LOCAL,
        authorization_url=fake.endpoints.authorize,
        token_url=fake.endpoints.token,
        userinfo_url=fake.endpoints.userinfo,
        client_id=client.client_id,
        client_secret=client.client_secret,
        redirect_uri=client.registered_redirect_uris[0],
        transaction_secret=SecretStr(generate_transaction_secret()),
        issuer=fake.endpoints.issuer,
        jwks_url=fake.endpoints.jwks,
    )


def _create_client(
    settings: GovBrSettings,
) -> Callable[[httpx.AsyncClient], GovBrClient]:
    """Prepare the common OAuth client composition used by each provider."""
    transactions = EncryptedTransactionCodec(settings.transaction_secret)
    validator = IdTokenValidator(settings=settings)

    def create(http: httpx.AsyncClient) -> GovBrClient:
        return GovBrClient(settings, transactions, validator, http)

    return create
