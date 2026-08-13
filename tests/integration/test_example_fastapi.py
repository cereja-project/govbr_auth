"""Smoke-test the executable FastAPI example against explicit fake providers."""

import importlib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from govbr_auth.fake import (
    FakeClient,
    FakeGovBrProvider,
    FakeGovBrSettings,
    FakeSigningKey,
    FakeUser,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
    create_fake_govbr_app,
)

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
    for variable in (
        "GOVBR_ENVIRONMENT",
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_CLIENT_ID",
        "GOVBR_CLIENT_SECRET",
        "GOVBR_REDIRECT_URI",
        "GOVBR_TRANSACTION_SECRET",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("GOVBR_CLIENT_ID", "process-client")
    monkeypatch.chdir(tmp_path)
    example = importlib.import_module("examples.example_fastapi")

    settings = example.settings_from_environment()

    assert settings.client_id == "process-client"
    assert str(settings.authorization_url) == ("http://localhost/fake-govbr/authorize")


@pytest.mark.asyncio
async def test_recommended_development_bootstrap_completes_mounted_fake_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_base_url = "http://localhost/fake-govbr"
    callback_url = "http://localhost/auth/govbr/callback"
    monkeypatch.setenv("GOVBR_ENVIRONMENT", "local")
    monkeypatch.setenv("GOVBR_AUTHORIZATION_URL", f"{provider_base_url}/authorize")
    monkeypatch.setenv("GOVBR_TOKEN_URL", f"{provider_base_url}/token")
    monkeypatch.setenv("GOVBR_USERINFO_URL", f"{provider_base_url}/userinfo")
    monkeypatch.setenv("GOVBR_CLIENT_ID", "local-example-client")
    monkeypatch.setenv("GOVBR_CLIENT_SECRET", "local-example-secret")
    monkeypatch.setenv("GOVBR_REDIRECT_URI", callback_url)
    monkeypatch.setenv(
        "GOVBR_TRANSACTION_SECRET", Fernet.generate_key().decode("ascii")
    )
    monkeypatch.setenv("GOVBR_ISSUER", f"{provider_base_url}/")
    monkeypatch.setenv("GOVBR_JWKS_URL", f"{provider_base_url}/jwk")
    example = importlib.import_module("examples.example_fastapi")

    application = example.create_development_app(clock=lambda: FIXED_NOW)

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://localhost",
            follow_redirects=True,
        ) as client:
            response = await client.get("/auth/govbr/login")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "subject": "local-example-subject",
    }
    assert {
        "/auth/govbr/callback",
        "/auth/govbr/login",
        "/fake-govbr/authorize",
        "/fake-govbr/jwk",
        "/fake-govbr/login",
        "/fake-govbr/token",
        "/fake-govbr/userinfo",
    }.issubset(application.openapi()["paths"])


@pytest.mark.parametrize(
    "provider_base_url,client_id,client_secret",
    (
        ("http://localhost", "local-example-client", "local-example-secret"),
        ("http://127.0.0.1", "alternate-client", "alternate-secret"),
    ),
    ids=("localhost-provider", "loopback-provider"),
)
@pytest.mark.asyncio
async def test_example_completes_same_consumer_flow_after_provider_config_switch(
    monkeypatch: pytest.MonkeyPatch,
    provider_base_url: str,
    client_id: str,
    client_secret: str,
) -> None:
    callback_url = "http://localhost/auth/govbr/callback"
    issuer = f"{provider_base_url}/"
    artifact_secret = SecretStr(Fernet.generate_key().decode("ascii"))
    provider_settings = FakeGovBrSettings(
        base_url=issuer,
        issuer=issuer,
        artifact_secret=artifact_secret,
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id=client_id,
                client_secret=SecretStr(client_secret),
                registered_redirect_uris=(callback_url,),
            ),
        ),
    )
    provider = FakeGovBrProvider(
        settings=provider_settings,
        user_store=InMemoryFakeUserStore(
            (
                FakeUser(
                    sub="example-subject",
                    name="Example User",
                    email="example@example.test",
                    email_verified=True,
                ),
            )
        ),
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=FakeSigningKey.generate(kid="example-key"),
    )
    provider_app = create_fake_govbr_app(
        provider,
        automatic_subject="example-subject",
        clock=lambda: FIXED_NOW,
    )
    provider_transport = httpx.ASGITransport(app=provider_app)
    monkeypatch.setenv("GOVBR_ENVIRONMENT", "local")
    monkeypatch.setenv("GOVBR_AUTHORIZATION_URL", f"{provider_base_url}/authorize")
    monkeypatch.setenv("GOVBR_TOKEN_URL", f"{provider_base_url}/token")
    monkeypatch.setenv("GOVBR_USERINFO_URL", f"{provider_base_url}/userinfo")
    monkeypatch.setenv("GOVBR_CLIENT_ID", client_id)
    monkeypatch.setenv("GOVBR_CLIENT_SECRET", client_secret)
    monkeypatch.setenv("GOVBR_REDIRECT_URI", callback_url)
    monkeypatch.setenv(
        "GOVBR_TRANSACTION_SECRET", Fernet.generate_key().decode("ascii")
    )
    monkeypatch.setenv("GOVBR_ISSUER", issuer)
    monkeypatch.setenv("GOVBR_JWKS_URL", f"{provider_base_url}/jwk")
    example = importlib.import_module("examples.example_fastapi")
    consumer_app = example.create_app(
        provider_transport=provider_transport,
        clock=lambda: FIXED_NOW,
    )

    async with consumer_app.router.lifespan_context(consumer_app):
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=consumer_app),
                base_url="http://localhost",
                follow_redirects=False,
            ) as consumer_http,
            httpx.AsyncClient(
                transport=provider_transport,
                base_url=provider_base_url,
                follow_redirects=False,
            ) as provider_http,
        ):
            login_response = await consumer_http.get("/auth/govbr/login")
            authorize_response = await provider_http.get(
                login_response.headers["location"]
            )
            callback_location = urlsplit(authorize_response.headers["location"])
            callback_response = await consumer_http.get(
                urlunsplit(
                    (
                        "",
                        "",
                        callback_location.path,
                        callback_location.query,
                        callback_location.fragment,
                    )
                )
            )

    consumer_routes = {
        path
        for path in consumer_app.openapi()["paths"]
        if path.startswith("/auth/govbr")
    }
    assert consumer_routes == {"/auth/govbr/callback", "/auth/govbr/login"}
    assert callback_response.status_code == 200
    assert callback_response.json() == {
        "authenticated": True,
        "subject": "example-subject",
    }
