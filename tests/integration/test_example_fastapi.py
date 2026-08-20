"""Smoke-test the executable example through the canonical FastAPI facade."""

import importlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def test_example_loads_only_the_working_directory_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    example = importlib.import_module("examples.example_fastapi")
    loaded: dict[str, object] = {}

    def record_load_dotenv(*, dotenv_path: Path, override: bool) -> bool:
        loaded.update(dotenv_path=dotenv_path, override=override)
        return False

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(example, "load_dotenv", record_load_dotenv)
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")

    example.create_app(clock=lambda: FIXED_NOW)

    assert loaded == {"dotenv_path": tmp_path / ".env", "override": False}


def test_example_uses_only_the_canonical_fastapi_facade() -> None:
    source = (Path(__file__).parents[2] / "examples" / "example_fastapi.py").read_text(
        encoding="utf-8"
    )

    assert "from govbr_auth.fastapi import AuthContext, GovBrAuth" in source
    assert "GovBrAuth(" in source
    assert "application.include_router(auth.router)" in source
    assert "FakeGovBrProvider" not in source
    assert "create_fake_govbr_router" not in source
    assert "settings_from_environment" not in source
    assert '"subject"' not in source


@pytest.mark.asyncio
async def test_example_selects_complete_fake_graph_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")
    for variable in (
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
    example = importlib.import_module("examples.example_fastapi")
    application = example.create_app(clock=lambda: FIXED_NOW)

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            response = await client.get("/auth/govbr/login")

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "http://127.0.0.1:8000/fake-govbr/authorize?"
    )
    assert {
        "/auth/govbr/callback",
        "/auth/govbr/login",
        "/fake-govbr/authorize",
        "/fake-govbr/jwk",
        "/fake-govbr/login",
        "/fake-govbr/token",
        "/fake-govbr/userinfo",
    }.issubset(application.openapi()["paths"])
