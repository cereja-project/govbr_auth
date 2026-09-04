"""Tests for the shared, framework-neutral adapter composition."""

from datetime import UTC, datetime

import pytest

from govbr_auth.adapters._application import create_adapter_application
from govbr_auth.fake.http.transport import FakeGovHttpTransport
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

FIXED_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_adapter_application_composes_runtime_service_and_paths() -> None:
    application = create_adapter_application(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        runtime=None,
        prefix="/oauth/govbr",
        expose_tokens=True,
        clock=lambda: FIXED_NOW,
        user_repository=None,
        fake_transport_factory=lambda fake: FakeGovHttpTransport(
            fake,
            clock=lambda: FIXED_NOW,
        ),
    )

    try:
        assert application.runtime.provider is GovBrProvider.FAKE
        assert application.service._client is application.runtime.client
        assert application.service._expose_tokens is True
        assert application.login_path == "/oauth/govbr/login"
        assert application.callback_path == "/oauth/govbr/callback"
        assert application.clock() is FIXED_NOW
    finally:
        await application.aclose()
