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
    ("name", "commands"),
    (
        (
            "django",
            (
                ("-m", "django", "check", "--settings=django_app"),
                (
                    "-c",
                    "from django_app import urlpatterns; "
                    "assert any(str(pattern.pattern) == 'govbr-auth-demo' "
                    "for pattern in urlpatterns)",
                ),
            ),
        ),
        (
            "flask",
            (
                (
                    "-c",
                    "from flask_app import app; "
                    "assert any(rule.rule == '/govbr-auth-demo' "
                    "for rule in app.url_map.iter_rules())",
                ),
            ),
        ),
    ),
)
def test_documented_framework_quickstart_is_executable(
    tmp_path: Path, name: str, commands: tuple[tuple[str, ...], ...]
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
        "GOVBR_FAKE_USERS_FILE": str(users),
        "GOVBR_PROVIDER": "fake",
        "GOVBR_DEMO_PAGE": "true",
        "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONUTF8": "1",
    }

    for command in commands:
        result = subprocess.run(
            [sys.executable, *command],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
