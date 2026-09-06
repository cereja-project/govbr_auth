"""Execute the public README quickstart against the source checkout."""

import os
from pathlib import Path
import re
import subprocess
import sys

from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

PROJECT_ROOT = Path(__file__).parents[2]
QUICKSTART = re.compile(
    r"<!-- quickstart-fastapi:start -->\s*```python\s*(.*?)\s*```\s*"
    r"<!-- quickstart-fastapi:end -->",
    re.DOTALL,
)
EXPLICIT_FAKE_SETTINGS = re.compile(
    r"<!-- settings-fake:start -->\s*```python\s*(.*?)\s*```\s*"
    r"<!-- settings-fake:end -->",
    re.DOTALL,
)
EXPLICIT_OFFICIAL_SETTINGS = re.compile(
    r"<!-- settings-official:start -->\s*```python\s*(.*?)\s*```\s*"
    r"<!-- settings-official:end -->",
    re.DOTALL,
)


def test_readme_fastapi_quickstart_opens_the_fake_login(tmp_path: Path) -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = QUICKSTART.search(readme)
    assert match is not None, "README quickstart markers are missing"
    (tmp_path / "myapp.py").write_text(match.group(1), encoding="utf-8")
    (tmp_path / "fake-users.local.json").write_text(
        '{"users": [{"cpf": "11122233344", "password": "senha-ficticia", '
        '"name": "Usuário Fake", "email": "fake@example.test"}]}',
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "GOVBR_PROVIDER=fake\n" "GOVBR_FAKE_USERS_FILE=./fake-users.local.json\n",
        encoding="utf-8",
    )

    probe = """
import httpx
from myapp import app

async def verify():
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://127.0.0.1:8000',
            follow_redirects=False,
        ) as client:
            login = await client.get('/auth/govbr/login')
            assert login.status_code == 302
            provider = await client.get(login.headers['location'])
            assert provider.status_code == 200
            assert 'name="request"' in provider.text

import asyncio
asyncio.run(verify())
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env={
            **{
                name: value
                for name, value in os.environ.items()
                if not name.startswith("GOVBR_")
            },
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(PROJECT_ROOT),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_readme_fastapi_quickstart_runs_as_a_python_program(
    tmp_path: Path,
) -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = QUICKSTART.search(readme)
    assert match is not None, "README quickstart markers are missing"
    (tmp_path / "myapp.py").write_text(match.group(1), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "GOVBR_PROVIDER=fake\n",
        encoding="utf-8",
    )

    probe = """
import asyncio
import runpy
from types import SimpleNamespace
import uvicorn
from govbr_auth.runtime import GovBrProvider

calls = []

def record_run(application, **options):
    calls.append((application, options))

def route_paths(application):
    paths = set()
    pending = list(application.routes)
    while pending:
        route = pending.pop()
        if path := getattr(route, 'path', None):
            paths.add(path)
        elif included := getattr(route, 'original_router', None):
            pending.extend(included.routes)
    return paths

uvicorn.run = record_run
namespace = runpy.run_path('myapp.py', run_name='__main__')
assert len(calls) == 1
assert calls[0][0] is namespace['app']
assert calls[0][1] == {
    'host': '127.0.0.1',
    'port': 8000,
    'log_level': 'info',
}
assert namespace['settings'].provider is GovBrProvider.FAKE
assert '/auth/govbr/login' in route_paths(namespace['app'])

malicious_context = SimpleNamespace(
    user=SimpleNamespace(
        name='<script>alert(1)</script>',
        sub='<script>alert(1)</script>',
    )
)
response = asyncio.run(namespace['authenticated'](malicious_context))
assert response.media_type == 'application/json'
assert b'<script>' not in response.body
assert response.body == b'{"authenticated":true}'
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env={
            **{
                name: value
                for name, value in os.environ.items()
                if not name.startswith("GOVBR_")
            },
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(PROJECT_ROOT),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_readme_explicit_fake_settings_block_is_executable() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = EXPLICIT_FAKE_SETTINGS.search(readme)
    assert match is not None, "README explicit FakeGov settings markers are missing"
    namespace = {
        "Path": Path,
        "GovBrProvider": GovBrProvider,
        "GovBrRuntimeSettings": GovBrRuntimeSettings,
        "create_app": lambda settings: settings,
    }

    exec(compile(match.group(1), "README.md", "exec"), namespace)

    settings = namespace["settings"]
    assert isinstance(settings, GovBrRuntimeSettings)
    assert settings.provider is GovBrProvider.FAKE
    assert settings.fake_users_file == Path("fake-users.local.json")
    assert namespace["app"] is settings


def test_readme_explicit_official_settings_block_is_executable(
    monkeypatch,
) -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = EXPLICIT_OFFICIAL_SETTINGS.search(readme)
    assert match is not None, "README official settings markers are missing"
    monkeypatch.setenv("GOVBR_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOVBR_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "GOVBR_REDIRECT_URI", "https://consumer.example.test/oauth/callback"
    )
    monkeypatch.setenv("GOVBR_TRANSACTION_SECRET", "test-transaction-secret")
    namespace = {
        "GovBrRuntimeSettings": GovBrRuntimeSettings,
        "create_app": lambda settings: settings,
    }

    exec(compile(match.group(1), "README.md", "exec"), namespace)

    settings = namespace["settings"]
    assert isinstance(settings, GovBrRuntimeSettings)
    assert settings.provider is GovBrProvider.OFFICIAL
    assert settings.oauth is not None
    assert settings.oauth.environment.value == "staging"
    assert namespace["app"] is settings
