"""Specify the reduced v1 adapter and runtime configuration surface."""

from pathlib import Path
import inspect

import pytest
from fastapi.responses import Response

import govbr_auth.runtime as runtime_module
from govbr_auth.fastapi import GovBrAuth
from govbr_auth.django import GovBrAuth as DjangoGovBrAuth
from govbr_auth.flask import GovBrAuth as FlaskGovBrAuth
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

PROJECT_ROOT = Path(__file__).parents[2]


@pytest.mark.asyncio
async def test_fastapi_accepts_runtime_settings_directly() -> None:
    async def success_handler(context: object) -> Response:
        del context
        return Response(status_code=204)

    auth = GovBrAuth(
        on_success=success_handler,
        settings=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
    )

    try:
        assert auth.runtime.provider is GovBrProvider.FAKE
    finally:
        await auth.runtime.aclose()


def test_fastapi_does_not_accept_demo_page_argument() -> None:
    async def success_handler(context: object) -> Response:
        del context
        return Response(status_code=204)

    with pytest.raises(TypeError, match="unexpected keyword argument 'demo_page'"):
        GovBrAuth(on_success=success_handler, demo_page=True)


def test_application_settings_module_and_runtime_export_are_removed() -> None:
    assert not (PROJECT_ROOT / "govbr_auth" / "application_settings.py").exists()
    assert not hasattr(runtime_module, "GovBrApplicationSettings")


def test_framework_adapters_share_the_small_runtime_surface() -> None:
    for adapter in (GovBrAuth, DjangoGovBrAuth, FlaskGovBrAuth):
        parameters = inspect.signature(adapter).parameters
        assert "settings" in parameters
        assert "runtime" in parameters
        assert "demo_page" not in parameters
