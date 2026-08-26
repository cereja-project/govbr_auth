"""Install a wheel in isolation and smoke-test every public adapter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import venv

_PROBE = r"""
import asyncio
from importlib.metadata import version
from pathlib import Path
import sys

import httpx
from django.conf import settings as django_settings
from flask import Flask, jsonify

import govbr_auth
from govbr_auth.django import GovBrAuth as DjangoGovBrAuth
from govbr_auth.fake.fastapi import create_fake_app
from govbr_auth.flask import GovBrAuth as FlaskGovBrAuth
from myapp import app as fastapi_app


assert Path(govbr_auth.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert govbr_auth.__version__ == version("govbr-auth")
if not django_settings.configured:
    django_settings.configure(
        ALLOWED_HOSTS=["testserver"],
        DEBUG=True,
        ROOT_URLCONF=__name__,
        SECRET_KEY="fake-local-only",
    )
import django
django.setup()


def django_success(context, request):
    from django.http import JsonResponse
    return JsonResponse({"authenticated": True})


django_auth = DjangoGovBrAuth(on_success=django_success)
urlpatterns = django_auth.urlpatterns
assert urlpatterns


flask_app = Flask(__name__)


def flask_success(context, request):
    return jsonify({"authenticated": True})


flask_auth = FlaskGovBrAuth(on_success=flask_success)
flask_auth.register(flask_app)
assert any(rule.rule == "/auth/govbr/login" for rule in flask_app.url_map.iter_rules())


async def verify_http_boundaries():
    async with fastapi_app.router.lifespan_context(fastapi_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            assert (await client.get("/auth/govbr/login")).status_code == 302

    fake_app = create_fake_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake_app),
        base_url="http://127.0.0.1:8000",
    ) as client:
        response = await client.get("/fake-govbr/jwk")
        assert response.status_code == 200
        assert response.json()["keys"]


asyncio.run(verify_http_boundaries())
django_auth.close()
flask_auth.close()
print(f"verified govbr-auth {govbr_auth.__version__} from {govbr_auth.__file__}")
"""


def _python_path(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def verify_distribution(wheel: Path, readme: Path) -> None:
    """Install ``wheel`` with every adapter and execute consumer smokes."""
    resolved_wheel = wheel.resolve(strict=True)
    readme_source = readme.resolve(strict=True).read_text(encoding="utf-8")
    quickstart = re.search(
        r"<!-- quickstart-fastapi:start -->\s*```python\s*(.*?)\s*```\s*"
        r"<!-- quickstart-fastapi:end -->",
        readme_source,
        re.DOTALL,
    )
    if quickstart is None:
        raise ValueError("README FastAPI quickstart markers are missing")
    with tempfile.TemporaryDirectory(prefix="govbr-auth-wheel-") as directory:
        root = Path(directory)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _python_path(environment)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"{resolved_wheel}[fastapi,django,flask,fake]",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run([str(python), "-m", "pip", "check"], cwd=root, check=True)

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
        probe = root / "probe.py"
        probe.write_text(_PROBE, encoding="utf-8")
        (root / "myapp.py").write_text(quickstart.group(1), encoding="utf-8")
        child_environment = {
            **os.environ,
            "GOVBR_FAKE_END_TO_END": "true",
            "GOVBR_FAKE_USERS_FILE": str(users_file),
            "GOVBR_PROVIDER": "fake",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "",
            "PYTHONUTF8": "1",
        }
        subprocess.run(
            [str(python), str(probe)],
            cwd=root,
            env=child_environment,
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    arguments = parser.parse_args()
    verify_distribution(arguments.wheel, arguments.readme)


if __name__ == "__main__":
    main()
