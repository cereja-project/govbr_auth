"""Verify that neutral modules do not import web frameworks transitively."""

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]


def test_neutral_modules_import_with_frameworks_blocked() -> None:
    code = """
import builtins

blocked = {"fastapi", "django", "flask", "starlette", "werkzeug", "asgiref"}
real_import = builtins.__import__


def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise AssertionError(f"blocked framework imported: {name}")
    return real_import(name, *args, **kwargs)


builtins.__import__ = guarded_import
import govbr_auth.core
import govbr_auth.runtime
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_fake_runtime_exposes_one_neutral_http_application_without_frameworks() -> None:
    code = """
import builtins
from dataclasses import fields
from datetime import UTC, datetime

import httpx

blocked = {"fastapi", "django", "flask", "starlette", "werkzeug", "asgiref"}
real_import = builtins.__import__


def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise AssertionError(f"blocked framework imported: {name}")
    return real_import(name, *args, **kwargs)


builtins.__import__ = guarded_import

from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings, create_govbr_runtime

runtime = create_govbr_runtime(
    GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_end_to_end=True,
        fake_redirect_uri="http://127.0.0.1:8000/auth/govbr/callback",
    ),
    fake_transport_factory=lambda _: httpx.MockTransport(
        lambda request: httpx.Response(500, request=request)
    ),
    clock=lambda: datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
)
fake = runtime.fake
assert fake is not None
http_applications = [
    getattr(fake, field.name)
    for field in fields(fake)
    if type(getattr(fake, field.name)).__name__ == "FakeGovHttpApplication"
]
assert len(http_applications) == 1, (
    f"expected one neutral HTTP application object, found {len(http_applications)}"
)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
