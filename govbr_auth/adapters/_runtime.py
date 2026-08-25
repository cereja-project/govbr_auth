"""Shared runtime composition for framework adapters."""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from govbr_auth.adapters._lifecycle import RuntimeOwner
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
    _fake_callback_url,
    create_govbr_runtime,
)
from govbr_auth.runtime_settings import _is_canonical_path_prefix

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeGovBrRuntime, FakeUserRepository


def create_adapter_runtime(
    *,
    settings: GovBrRuntimeSettings | None,
    runtime: GovBrRuntime | None,
    prefix: str,
    clock: Callable[[], datetime],
    user_repository: "FakeUserRepository | None",
    fake_transport_factory: Callable[["FakeGovBrRuntime"], httpx.AsyncBaseTransport],
) -> RuntimeOwner:
    """Create or borrow one canonical runtime for a framework adapter."""
    if settings is not None and runtime is not None:
        raise TypeError("settings and runtime are mutually exclusive")
    if not _is_canonical_path_prefix(prefix, allow_empty=True):
        raise ValueError("prefix must be an empty string or a canonical path")

    if runtime is None:
        resolved_settings = settings or GovBrRuntimeSettings.from_environment()
        if resolved_settings.provider is GovBrProvider.FAKE:
            resolved_settings = _settings_for_fake_callback(resolved_settings, prefix)
            runtime = create_govbr_runtime(
                resolved_settings,
                fake_transport_factory=fake_transport_factory,
                clock=clock,
                user_repository=user_repository,
            )
        else:
            runtime = create_govbr_runtime(
                resolved_settings,
                clock=clock,
                user_repository=user_repository,
            )
        return RuntimeOwner(runtime=runtime, owns_runtime=True)

    _validate_runtime_callback(runtime, prefix)
    return RuntimeOwner(runtime=runtime, owns_runtime=False)


def _settings_for_fake_callback(
    settings: GovBrRuntimeSettings,
    prefix: str,
) -> GovBrRuntimeSettings:
    expected = _fake_callback_url(settings.fake_host, settings.fake_port, prefix)
    configured = None if settings.fake_redirect_uri is None else str(settings.fake_redirect_uri)
    default = _fake_callback_url(
        settings.fake_host,
        settings.fake_port,
        "/auth/govbr",
    )
    if configured is not None and configured not in {default, expected}:
        raise ValueError("fake redirect URI does not match the adapter callback")
    values = settings.model_dump()
    values["fake_redirect_uri"] = expected
    return GovBrRuntimeSettings.model_validate(values)


def _validate_runtime_callback(runtime: GovBrRuntime, prefix: str) -> None:
    if runtime.fake is None:
        return
    expected = _fake_callback_url(
        runtime.settings.fake_host,
        runtime.settings.fake_port,
        prefix,
    )
    configured = str(runtime.fake.settings.clients[0].registered_redirect_uris[0])
    if configured != expected:
        raise ValueError("fake runtime redirect URI does not match the adapter callback")
