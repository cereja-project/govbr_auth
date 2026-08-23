"""Characterize the internal boundaries introduced by the refactoring."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_client_imports_split_http_modules_without_legacy_facade() -> None:
    """The client must consume the extracted collaborators directly."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import builtins\n"
                "real_import = builtins.__import__\n"
                "def guarded_import(name, *args, **kwargs):\n"
                "    fromlist = args[2] if len(args) > 2 else ()\n"
                "    if name == 'govbr_auth.core.http' or (\n"
                "        name == 'govbr_auth.core' and 'http' in fromlist\n"
                "    ):\n"
                "        raise AssertionError('legacy HTTP facade imported')\n"
                "    return real_import(name, *args, **kwargs)\n"
                "builtins.__import__ = guarded_import\n"
                "import govbr_auth.core.client\n"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
