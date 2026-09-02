"""Execute the standalone Django and Flask snippets published in the guide."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
README = PROJECT_ROOT / "README.md"
GUIDE = PROJECT_ROOT / "docs" / "guide" / "quick-start.rst"
FAKE_MODE_GUIDE = PROJECT_ROOT / "docs" / "guide" / "fake-mode.rst"


def _snippet(name: str) -> str:
    source = GUIDE.read_text(encoding="utf-8")
    start = f".. quickstart-{name}:start"
    end = f".. quickstart-{name}:end"
    assert start in source and end in source
    block = source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]
    code = block.split(".. code-block:: python", maxsplit=1)[1]
    return textwrap.dedent(code).strip() + "\n"


def _readme_fastapi_snippet() -> str:
    source = README.read_text(encoding="utf-8")
    start = "<!-- quickstart-fastapi:start -->"
    end = "<!-- quickstart-fastapi:end -->"
    block = source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]
    return (
        block.split("```python", maxsplit=1)[1].split("```", maxsplit=1)[0].strip()
        + "\n"
    )


def _first_rst_python_snippet(document: Path) -> str:
    source = document.read_text(encoding="utf-8")
    block = source.split(".. code-block:: python", maxsplit=1)[1]
    lines: list[str] = []
    for line in block.splitlines():
        if not lines and not line.strip():
            continue
        if line.startswith("    ") or not line.strip():
            lines.append(line)
            continue
        break
    return textwrap.dedent("\n".join(lines)).strip() + "\n"


def _public_snippet(name: str) -> str:
    if name == "readme-fastapi":
        return _readme_fastapi_snippet()
    if name == "quick-start-fastapi":
        return _first_rst_python_snippet(GUIDE)
    if name == "fake-mode-fastapi":
        return _first_rst_python_snippet(FAKE_MODE_GUIDE)
    return _snippet(name)


@pytest.mark.parametrize(
    ("name", "module_name"),
    (
        ("readme-fastapi", "myapp"),
        ("quick-start-fastapi", "myapp"),
        ("fake-mode-fastapi", "myapp"),
        ("django", "django_app"),
        ("flask", "flask_app"),
    ),
)
def test_documented_quickstart_does_not_load_dotenv_from_parent_directory(
    tmp_path: Path,
    name: str,
    module_name: str,
) -> None:
    (tmp_path / ".env").write_text(
        "ANCESTOR_DOTENV_MARKER=loaded\n",
        encoding="utf-8",
    )
    application_root = tmp_path / "application"
    application_root.mkdir()
    (application_root / f"{module_name}.py").write_text(
        _public_snippet(name),
        encoding="utf-8",
    )
    environment = {
        **{
            variable: value
            for variable, value in os.environ.items()
            if not variable.startswith("GOVBR_")
            and variable != "ANCESTOR_DOTENV_MARKER"
        },
        "GOVBR_PROVIDER": "fake",
        "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONUTF8": "1",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import os; import {module_name}; "
            "assert 'ANCESTOR_DOTENV_MARKER' not in os.environ",
        ],
        cwd=application_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


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
