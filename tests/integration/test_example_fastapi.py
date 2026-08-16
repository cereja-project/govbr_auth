"""Smoke-test the executable example through the canonical FastAPI facade."""

import importlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def test_settings_from_environment_loads_dotenv_without_overriding_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            (
                "GOVBR_ENVIRONMENT=local",
                "GOVBR_AUTHORIZATION_URL=http://localhost/fake-govbr/authorize",
                "GOVBR_TOKEN_URL=http://localhost/fake-govbr/token",
                "GOVBR_USERINFO_URL=http://localhost/fake-govbr/userinfo",
                "GOVBR_CLIENT_ID=dotenv-client",
                "GOVBR_CLIENT_SECRET=dotenv-secret",
                "GOVBR_REDIRECT_URI=http://localhost/auth/govbr/callback",
                f"GOVBR_TRANSACTION_SECRET={Fernet.generate_key().decode('ascii')}",
                "GOVBR_ISSUER=http://localhost/fake-govbr/",
                "GOVBR_JWKS_URL=http://localhost/fake-govbr/jwk",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOVBR_CLIENT_ID", "process-client")
    monkeypatch.chdir(tmp_path)
    example = importlib.import_module("examples.example_fastapi")

    settings = example.settings_from_environment()

    assert settings.client_id == "process-client"
    assert str(settings.authorization_url) == "http://localhost/fake-govbr/authorize"


def test_example_uses_only_the_canonical_fastapi_facade() -> None:
    source = (Path(__file__).parents[2] / "examples" / "example_fastapi.py").read_text(
        encoding="utf-8"
    )

    assert "from govbr_auth.fastapi import AuthContext, GovBrAuth" in source
    assert "GovBrAuth(" in source
    assert "application.include_router(auth.router)" in source
    assert "FakeGovBrProvider" not in source
    assert "create_fake_govbr_router" not in source


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
