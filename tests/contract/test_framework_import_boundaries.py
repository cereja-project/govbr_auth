"""Verify that neutral modules do not import web frameworks transitively."""

from textwrap import dedent
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_fastapi_adapter_import_does_not_require_asgiref() -> None:
    code = dedent("""
        import builtins

        real_import = builtins.__import__


        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".", 1)[0] == "asgiref":
                raise AssertionError("FastAPI adapter imported asgiref")
            return real_import(name, globals, locals, fromlist, level)


        builtins.__import__ = guarded_import
        import govbr_auth.fastapi
        """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_neutral_modules_import_with_frameworks_blocked() -> None:
    code = dedent("""
        import builtins
        import sys

        blocked = {"fastapi", "django", "flask", "starlette", "werkzeug", "asgiref"}
        real_import = builtins.__import__


        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".", 1)[0]
            blocked_fromlist = [
                item
                for item in (fromlist or ())
                if item.split(".", 1)[0] in blocked
            ]
            if root in blocked or blocked_fromlist:
                detail = ", ".join(blocked_fromlist) if blocked_fromlist else name
                raise AssertionError(f"blocked framework imported: {detail}")
            return real_import(name, globals, locals, fromlist, level)


        builtins.__import__ = guarded_import
        import govbr_auth.core.client
        import govbr_auth.application_settings
        import govbr_auth.runtime
        import govbr_auth.fake.runtime

        assert not blocked.intersection(sys.modules)
        """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_fake_runtime_exposes_one_neutral_http_application_without_frameworks() -> None:
    code = dedent("""
        import builtins
        from datetime import UTC, datetime

        import httpx

        blocked = {"fastapi", "django", "flask", "starlette", "werkzeug", "asgiref"}
        real_import = builtins.__import__


        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".", 1)[0]
            blocked_fromlist = [
                item
                for item in (fromlist or ())
                if item.split(".", 1)[0] in blocked
            ]
            if root in blocked or blocked_fromlist:
                detail = ", ".join(blocked_fromlist) if blocked_fromlist else name
                raise AssertionError(f"blocked framework imported: {detail}")
            return real_import(name, globals, locals, fromlist, level)


        builtins.__import__ = guarded_import

        from govbr_auth.runtime import (
            GovBrProvider,
            GovBrRuntimeSettings,
            create_govbr_runtime,
        )

        runtime = create_govbr_runtime(
            GovBrRuntimeSettings(
                provider=GovBrProvider.FAKE,
                fake_redirect_uri="http://127.0.0.1:8000/auth/govbr/callback",
            ),
            fake_transport_factory=lambda _: httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            ),
            clock=lambda: datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
        )
        fake = runtime.fake
        assert fake is not None
        assert fake.prefix == "/fake-govbr"
        assert fake.endpoints.authorize.endswith("/authorize")
        assert fake.endpoints.token.endswith("/token")
        """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
