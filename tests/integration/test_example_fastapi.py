"""Smoke-test the executable example through the canonical FastAPI facade."""

import importlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import dotenv

from examples.example_settings import runtime_settings

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (
        "GOVBR_PROVIDER",
        "GOVBR_ENVIRONMENT",
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_CLIENT_ID",
        "GOVBR_CLIENT_SECRET",
        "GOVBR_REDIRECT_URI",
        "GOVBR_SCOPE",
        "GOVBR_TRANSACTION_SECRET",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
        "GOVBR_CONNECT_TIMEOUT_SECONDS",
        "GOVBR_READ_TIMEOUT_SECONDS",
        "GOVBR_CLOCK_SKEW_SECONDS",
        "GOVBR_FAKE_END_TO_END",
        "GOVBR_FAKE_HOST",
        "GOVBR_FAKE_PORT",
        "GOVBR_FAKE_PROVIDER_PREFIX",
        "GOVBR_FAKE_CLIENT_ID",
        "GOVBR_FAKE_CLIENT_SECRET",
        "GOVBR_FAKE_REDIRECT_URI",
        "GOVBR_FAKE_REQUEST_TTL_SECONDS",
        "GOVBR_FAKE_AUTHORIZATION_CODE_TTL_SECONDS",
        "GOVBR_FAKE_ACCESS_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_ID_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_USERS_FILE",
    ):
        monkeypatch.delenv(variable, raising=False)


def test_example_settings_preserve_complete_fake_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "fake-users.json"
    configured = {
        "GOVBR_PROVIDER": "fake",
        "GOVBR_FAKE_END_TO_END": "false",
        "GOVBR_FAKE_HOST": "localhost",
        "GOVBR_FAKE_PORT": "8123",
        "GOVBR_FAKE_PROVIDER_PREFIX": "/provider",
        "GOVBR_FAKE_CLIENT_ID": "example-client",
        "GOVBR_FAKE_CLIENT_SECRET": "example-secret",
        "GOVBR_FAKE_REDIRECT_URI": "http://localhost:8123/auth/govbr/callback",
        "GOVBR_FAKE_REQUEST_TTL_SECONDS": "11",
        "GOVBR_FAKE_AUTHORIZATION_CODE_TTL_SECONDS": "12",
        "GOVBR_FAKE_ACCESS_TOKEN_TTL_SECONDS": "13",
        "GOVBR_FAKE_ID_TOKEN_TTL_SECONDS": "14",
        "GOVBR_FAKE_USERS_FILE": str(users_file),
    }
    for variable, value in configured.items():
        monkeypatch.setenv(variable, value)

    settings = runtime_settings()

    assert settings.provider.value == "fake"
    assert settings.fake_end_to_end is False
    assert settings.fake_host == "localhost"
    assert settings.fake_port == 8123
    assert settings.fake_provider_prefix == "/provider"
    assert settings.fake_client_id == "example-client"
    assert settings.fake_client_secret.get_secret_value() == "example-secret"
    assert str(settings.fake_redirect_uri) == (
        "http://localhost:8123/auth/govbr/callback"
    )
    assert settings.fake_request_ttl_seconds == 11
    assert settings.fake_authorization_code_ttl_seconds == 12
    assert settings.fake_access_token_ttl_seconds == 13
    assert settings.fake_id_token_ttl_seconds == 14
    assert settings.fake_users_file == users_file


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
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
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


def test_flask_example_loads_provider_from_working_directory_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    example = importlib.import_module("examples.example_flask")
    loaded: dict[str, object] = {}

    def record_load_dotenv(*, dotenv_path: Path, override: bool) -> bool:
        loaded.update(dotenv_path=dotenv_path, override=override)
        return False

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(example, "load_dotenv", record_load_dotenv, raising=False)
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")

    example.create_app()

    assert loaded == {"dotenv_path": tmp_path / ".env", "override": False}


def test_django_example_loads_provider_from_working_directory_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    loaded: dict[str, object] = {}

    def record_load_dotenv(*, dotenv_path: Path, override: bool) -> bool:
        loaded.update(dotenv_path=dotenv_path, override=override)
        return False

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dotenv, "load_dotenv", record_load_dotenv)
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")
    example = importlib.reload(importlib.import_module("examples.example_django"))

    try:
        assert example.auth._owner.runtime.settings.provider.value == "fake"
        assert loaded == {"dotenv_path": tmp_path / ".env", "override": False}
    finally:
        example.auth.close()
