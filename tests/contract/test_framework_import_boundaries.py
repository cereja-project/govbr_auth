"""Verify that neutral modules do not import web frameworks transitively."""

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]


def test_neutral_modules_import_with_frameworks_blocked() -> None:
    code = """
import builtins

blocked = {"fastapi", "django", "flask", "starlette", "werkzeug"}
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

