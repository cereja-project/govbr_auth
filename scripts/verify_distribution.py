"""Install a wheel in isolation and smoke-test every public adapter."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import venv

_FASTAPI_PROBE = r"""
import asyncio
from importlib.metadata import version
from pathlib import Path
import sys

import httpx

import govbr_auth
from govbr_auth.fake.fastapi import create_fake_app
from govbr_auth.runtime import (
    GovBrApplicationSettings,
    GovBrProvider,
    GovBrRuntimeSettings,
)
from myapp import app as fastapi_app


assert Path(govbr_auth.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert govbr_auth.__version__ == version("govbr-auth")


async def verify_http_boundaries():
    async with fastapi_app.router.lifespan_context(fastapi_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            assert (await client.get("/auth/govbr/login")).status_code == 302
            demo = await client.get("/govbr-auth-demo")
            assert demo.status_code == 200
            assert "Entrar com gov.br" in demo.text

    provider_only_settings = GovBrApplicationSettings(
        runtime=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        demo_page=False,
    )
    fake_app = create_fake_app(provider_only_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake_app),
        base_url="http://127.0.0.1:8000",
    ) as client:
        response = await client.get("/jwk")
        assert response.status_code == 200
        assert response.json()["keys"]


asyncio.run(verify_http_boundaries())
print(f"verified govbr-auth {govbr_auth.__version__} from {govbr_auth.__file__}")
"""

_DEMO_DOCUMENTATION_SYMBOLS = (
    "GOVBR_DEMO_PAGE",
    "/govbr-auth-demo",
    "GovBrApplicationSettings.from_environment()",
    "Entrar com gov.br",
)


@dataclass(frozen=True, slots=True)
class DistributionProfile:
    """Describe one documented installation that must work by itself."""

    name: str
    extras: tuple[str, ...]


def distribution_profiles() -> tuple[DistributionProfile, ...]:
    """Return the independently installed public adapter profiles."""
    return (
        DistributionProfile("fastapi", ("fastapi", "fake")),
        DistributionProfile("django", ("django",)),
        DistributionProfile("flask", ("flask",)),
    )


def _python_path(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def _markdown_quickstart(source: str) -> str:
    match = re.search(
        r"<!-- quickstart-fastapi:start -->\s*```python\s*(.*?)\s*```\s*"
        r"<!-- quickstart-fastapi:end -->",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("README FastAPI quickstart markers are missing")
    return match.group(1).strip() + "\n"


def _rst_quickstart(source: str, name: str) -> str:
    start = f".. quickstart-{name}:start"
    end = f".. quickstart-{name}:end"
    if start not in source or end not in source:
        raise ValueError(f"guide {name} quickstart markers are missing")
    block = source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]
    if ".. code-block:: python" not in block:
        raise ValueError(f"guide {name} quickstart code block is missing")
    code = block.split(".. code-block:: python", maxsplit=1)[1]
    return textwrap.dedent(code).strip() + "\n"


def _validate_demo_documentation(source: str, document_name: str) -> None:
    """Require every packaged entry guide to describe the demo-page surface."""
    for symbol in _DEMO_DOCUMENTATION_SYMBOLS:
        if symbol not in source:
            raise ValueError(
                f"{document_name} is missing demo documentation symbol: {symbol}"
            )


def _install_profile(python: Path, wheel: Path, profile: DistributionProfile) -> None:
    extras = ",".join(profile.extras)
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            f"{wheel}[{extras}]",
        ],
        check=True,
    )
    subprocess.run([str(python), "-m", "pip", "check"], check=True)


def verify_distribution(wheel: Path, readme: Path, guide: Path) -> None:
    """Install each documented extra in isolation and execute its quickstart."""
    resolved_wheel = wheel.resolve(strict=True)
    readme_source = readme.resolve(strict=True).read_text(encoding="utf-8")
    guide_source = guide.resolve(strict=True).read_text(encoding="utf-8")
    _validate_demo_documentation(readme_source, readme.name)
    _validate_demo_documentation(guide_source, guide.name)
    snippets = {
        "fastapi": _markdown_quickstart(readme_source),
        "django": _rst_quickstart(guide_source, "django"),
        "flask": _rst_quickstart(guide_source, "flask"),
    }
    with tempfile.TemporaryDirectory(prefix="govbr-auth-wheel-") as directory:
        root = Path(directory)
        users_file = root / "fake-users.json"
        users_file.write_text(
            json.dumps(
                {
                    "users": [
                        {
                            "cpf": "11122233344",
                            "password": "senha-ficticia",
                            "name": "Usuário Fake",
                            "email": "fake@example.test",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        child_environment = {
            **os.environ,
            "GOVBR_DEMO_PAGE": "true",
            "GOVBR_FAKE_USERS_FILE": str(users_file),
            "GOVBR_PROVIDER": "fake",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "",
            "PYTHONUTF8": "1",
        }
        child_environment.pop("GOVBR_FAKE_END_TO_END", None)
        for profile in distribution_profiles():
            profile_root = root / profile.name
            profile_root.mkdir()
            environment = profile_root / "venv"
            venv.EnvBuilder(with_pip=True, clear=True).create(environment)
            python = _python_path(environment)
            _install_profile(python, resolved_wheel, profile)
            module_name = (
                "myapp.py" if profile.name == "fastapi" else f"{profile.name}_app.py"
            )
            (profile_root / module_name).write_text(
                snippets[profile.name],
                encoding="utf-8",
            )
            if profile.name == "fastapi":
                probe = profile_root / "probe.py"
                probe.write_text(_FASTAPI_PROBE, encoding="utf-8")
                command = (str(python), str(probe))
            elif profile.name == "django":
                command = (
                    str(python),
                    "-c",
                    "import os; "
                    "os.environ['DJANGO_SETTINGS_MODULE'] = 'django_app'; "
                    "import django; django.setup(); "
                    "from django.core.management import call_command; "
                    "call_command('check'); "
                    "from django_app import urlpatterns; "
                    "assert any(str(pattern.pattern) == 'govbr-auth-demo' "
                    "for pattern in urlpatterns)",
                )
            else:
                command = (
                    str(python),
                    "-c",
                    "from flask_app import app; "
                    "assert any(rule.rule == '/govbr-auth-demo' "
                    "for rule in app.url_map.iter_rules())",
                )
            subprocess.run(
                command,
                cwd=profile_root,
                env=child_environment,
                check=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument(
        "--guide",
        type=Path,
        default=Path("docs/guide/quick-start.rst"),
    )
    arguments = parser.parse_args()
    verify_distribution(arguments.wheel, arguments.readme, arguments.guide)


if __name__ == "__main__":
    main()
