"""Shared framework-neutral composition for consumer adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, cast

from govbr_auth.adapters._lifecycle import RuntimeOwner
from govbr_auth.adapters._runtime import (
    adapter_callback_path,
    create_adapter_runtime,
)
from govbr_auth.authentication import AuthenticationService
from govbr_auth.runtime import GovBrRuntime, GovBrRuntimeSettings

if TYPE_CHECKING:
    import httpx

    from govbr_auth.fake.runtime import FakeGovSimulator, FakeUserRepository


@dataclass(slots=True)
class AdapterApplication:
    """Hold the shared runtime, service, paths, and lifecycle for one adapter."""

    owner: RuntimeOwner
    service: AuthenticationService
    login_path: str
    callback_path: str
    logout_path: str | None
    clock: Callable[[], datetime]

    @property
    def runtime(self) -> GovBrRuntime:
        """Return the concrete runtime composed for this adapter."""
        return cast(GovBrRuntime, self.owner.runtime)

    def close(self) -> None:
        """Close an owned runtime synchronously."""
        self.owner.close()

    async def aclose(self) -> None:
        """Close an owned runtime asynchronously."""
        await self.owner.aclose()


def create_adapter_application(
    *,
    settings: GovBrRuntimeSettings | None,
    runtime: GovBrRuntime | None,
    prefix: str,
    expose_tokens: bool,
    clock: Callable[[], datetime],
    user_repository: "FakeUserRepository | None",
    fake_transport_factory: Callable[["FakeGovSimulator"], "httpx.AsyncBaseTransport"],
) -> AdapterApplication:
    """Compose the common runtime and authentication service once."""
    owner = create_adapter_runtime(
        settings=settings,
        runtime=runtime,
        prefix=prefix,
        clock=clock,
        user_repository=user_repository,
        fake_transport_factory=fake_transport_factory,
    )
    concrete_runtime = cast(GovBrRuntime, owner.runtime)
    oauth = concrete_runtime.settings.oauth
    return AdapterApplication(
        owner=owner,
        service=AuthenticationService(
            concrete_runtime.client,
            expose_tokens=expose_tokens,
        ),
        login_path=f"{prefix}/login" if prefix else "/login",
        callback_path=adapter_callback_path(concrete_runtime, prefix),
        logout_path=(
            (f"{prefix}/logout" if prefix else "/logout")
            if oauth is not None
            and oauth.logout_url is not None
            and oauth.post_logout_redirect_uri is not None
            else None
        ),
        clock=clock,
    )
