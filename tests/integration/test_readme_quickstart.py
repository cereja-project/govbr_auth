"""Execute the public README quickstart against the source checkout."""

import os
from pathlib import Path
import re
import subprocess
import sys

PROJECT_ROOT = Path(__file__).parents[2]
QUICKSTART = re.compile(
    r"<!-- quickstart-fastapi:start -->\s*```python\s*(.*?)\s*```\s*"
    r"<!-- quickstart-fastapi:end -->",
    re.DOTALL,
)


def test_readme_fastapi_quickstart_opens_the_fake_login(tmp_path: Path) -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = QUICKSTART.search(readme)
    assert match is not None, "README quickstart markers are missing"
    (tmp_path / "myapp.py").write_text(match.group(1), encoding="utf-8")

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
            **os.environ,
            "GOVBR_PROVIDER": "fake",
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(PROJECT_ROOT),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
