"""Execute the standalone Django and Flask snippets published in the guide."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
GUIDE = PROJECT_ROOT / "docs" / "guide" / "quick-start.rst"


def _snippet(name: str) -> str:
    source = GUIDE.read_text(encoding="utf-8")
    start = f".. quickstart-{name}:start"
    end = f".. quickstart-{name}:end"
    assert start in source and end in source
    block = source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]
    code = block.split(".. code-block:: python", maxsplit=1)[1]
    return textwrap.dedent(code).strip() + "\n"


@pytest.mark.parametrize(
    ("name", "command"),
    (
        ("django", ("-m", "django", "check", "--settings=django_app")),
        (
            "flask",
            (
                "-c",
                "from flask_app import app; "
                "assert any(rule.rule == '/auth/govbr/login' "
                "for rule in app.url_map.iter_rules())",
            ),
        ),
    ),
)
def test_documented_framework_quickstart_is_executable(
    tmp_path: Path, name: str, command: tuple[str, ...]
) -> None:
    (tmp_path / f"{name}_app.py").write_text(_snippet(name), encoding="utf-8")
    users = tmp_path / "fake-users.local.json"
    users.write_text(
        '{"users":[{"cpf":"11122233344","password":"senha-ficticia",'
        '"name":"Usuário Fake","email":"fake@example.test"}]}',
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "GOVBR_FAKE_END_TO_END": "true",
        "GOVBR_FAKE_USERS_FILE": str(users),
        "GOVBR_PROVIDER": "fake",
        "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONUTF8": "1",
    }

    result = subprocess.run(
        [sys.executable, *command],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
