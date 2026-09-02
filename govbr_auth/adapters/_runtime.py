"""Shared runtime composition for framework adapters."""

from collections.abc import Callable
from datetime import datetime
import re
from typing import TYPE_CHECKING
from urllib.parse import unquote

import httpx

from govbr_auth.adapters._lifecycle import RuntimeOwner
from govbr_auth.presentation import DEMO_PAGE_PATH
from govbr_auth.runtime import (
    GovBrApplicationSettings,
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
    create_govbr_runtime,
)
from govbr_auth.runtime_settings import (
    _fake_callback_url,
    _is_canonical_path_prefix,
)

if TYPE_CHECKING:
    from govbr_auth.fake.runtime import FakeGovSimulator, FakeUserRepository


def create_adapter_runtime(
    *,
    settings: GovBrApplicationSettings | None,
    runtime: GovBrRuntime | None,
    demo_page: bool,
    prefix: str,
    clock: Callable[[], datetime],
    user_repository: "FakeUserRepository | None",
    fake_transport_factory: Callable[["FakeGovSimulator"], httpx.AsyncBaseTransport],
) -> tuple[RuntimeOwner, bool]:
    """Create or borrow one canonical runtime for a framework adapter."""
    if settings is not None and runtime is not None:
        raise TypeError("settings and runtime are mutually exclusive")
    if settings is not None and demo_page:
        raise TypeError("demo_page must be configured in settings")

    if runtime is None:
        application_settings = settings or GovBrApplicationSettings.from_environment()
        resolved_settings = prepare_adapter_runtime_settings(
            application_settings,
            prefix=prefix,
        )
        owner = _create_owned_adapter_runtime(
            resolved_settings,
            clock=clock,
            user_repository=user_repository,
            fake_transport_factory=fake_transport_factory,
        )
        return owner, application_settings.demo_page

    _validate_adapter_prefix(prefix)
    _validate_runtime_callback(runtime, prefix)
    _validate_demo_page_callback(runtime.settings, prefix, demo_page)
    return RuntimeOwner(runtime=runtime, owns_runtime=False), demo_page


def _create_owned_adapter_runtime(
    settings: GovBrRuntimeSettings,
    *,
    clock: Callable[[], datetime],
    user_repository: "FakeUserRepository | None",
    fake_transport_factory: Callable[["FakeGovSimulator"], httpx.AsyncBaseTransport],
) -> RuntimeOwner:
    if settings.provider is GovBrProvider.FAKE:
        runtime = create_govbr_runtime(
            settings,
            fake_transport_factory=fake_transport_factory,
            clock=clock,
            user_repository=user_repository,
        )
    else:
        runtime = create_govbr_runtime(
            settings,
            clock=clock,
            user_repository=user_repository,
        )
    return RuntimeOwner(runtime=runtime, owns_runtime=True)


def prepare_adapter_runtime_settings(
    application_settings: GovBrApplicationSettings,
    *,
    prefix: str,
) -> GovBrRuntimeSettings:
    """Validate callback topology before allocating adapter runtime resources."""
    _validate_adapter_prefix(prefix)
    settings = application_settings.runtime
    _validate_demo_page_callback(
        settings,
        prefix,
        application_settings.demo_page,
    )
    if settings.provider is GovBrProvider.FAKE:
        settings = _settings_for_fake_callback(settings, prefix)
    adapter_settings_callback_path(settings, prefix)
    return settings


def _validate_adapter_prefix(prefix: str) -> None:
    if not _is_canonical_path_prefix(prefix, allow_empty=True):
        raise ValueError("prefix must be an empty string or a canonical path")


def adapter_callback_path(runtime: GovBrRuntime, prefix: str) -> str:
    """Resolve the consumer callback path from validated runtime settings."""
    return adapter_settings_callback_path(runtime.settings, prefix)


def adapter_settings_callback_path(
    settings: GovBrRuntimeSettings,
    prefix: str,
) -> str:
    """Resolve and validate the callback before allocating runtime resources."""
    if settings.provider is GovBrProvider.OFFICIAL and settings.oauth is not None:
        callback_path = _route_path(settings.oauth.redirect_uri.path or "/")
    else:
        callback_path = f"{prefix}/callback" if prefix else "/callback"

    login_path = f"{prefix}/login" if prefix else "/login"
    if callback_path == login_path:
        raise ValueError("redirect URI callback path must differ from the login path")
    return callback_path


def _validate_demo_page_callback(
    settings: GovBrRuntimeSettings,
    prefix: str,
    demo_page: bool,
) -> None:
    callback_path = adapter_settings_callback_path(settings, prefix)
    if (
        settings.provider is GovBrProvider.FAKE
        and settings.fake_redirect_uri is not None
    ):
        callback_path = _route_path(settings.fake_redirect_uri.path or "/")
    if demo_page and callback_path == DEMO_PAGE_PATH:
        raise ValueError(
            "redirect URI callback path must differ from the demo page path"
        )


def _route_path(encoded_path: str) -> str:
    """Decode one static URL path or reject ambiguous router syntax."""
    if re.search(r"%(?:2f|5c)", encoded_path, flags=re.IGNORECASE) or re.search(
        r"%(?![0-9a-f]{2})", encoded_path, flags=re.IGNORECASE
    ):
        raise ValueError("redirect URI path is not route-safe")
    try:
        path = unquote(encoded_path, errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("redirect URI path is not route-safe") from error

    segments = path[1:].split("/") if path.startswith("/") else []
    if (
        not path.startswith("/")
        or "//" in path
        or "\\" in path
        or any(character in path for character in "{}<>")
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or any(segment in {".", ".."} for segment in segments)
    ):
        raise ValueError("redirect URI path is not route-safe")
    return path


def _settings_for_fake_callback(
    settings: GovBrRuntimeSettings,
    prefix: str,
) -> GovBrRuntimeSettings:
    expected = _fake_callback_url(settings.fake_host, settings.fake_port, prefix)
    configured = (
        None if settings.fake_redirect_uri is None else str(settings.fake_redirect_uri)
    )
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
        raise ValueError(
            "fake runtime redirect URI does not match the adapter callback"
        )
