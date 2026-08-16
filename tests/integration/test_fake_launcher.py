"""Exercise the unified local Fake Gov.br launcher profiles."""

import json
import runpy
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from govbr_auth.fake import FakeUser, InMemoryFakeUserRepository, create_fake_app
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolate_fake_launcher_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep launcher profiles and user sources explicit in every test."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")
    monkeypatch.delenv("GOVBR_FAKE_END_TO_END", raising=False)
    monkeypatch.delenv("GOVBR_FAKE_USERS_FILE", raising=False)
    for variable in (
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ):
        monkeypatch.delenv(variable, raising=False)


@dataclass(frozen=True, slots=True)
class FakeLoginForm:
    """Capture the browser fields exposed by the fake-provider login form."""

    action: str
    request: str
    cpf_name: str
    password_name: str


class FakeLoginFormParser(HTMLParser):
    """Parse only the fields required to drive the browser-visible flow."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.request: str | None = None
        self.cpf_name: str | None = None
        self.password_name: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "form":
            self.action = values.get("action")
        elif tag == "input":
            name = values.get("name")
            if name == "request":
                self.request = values.get("value")
            elif name == "cpf":
                self.cpf_name = name
            elif name == "password":
                self.password_name = name


def parse_fake_login_form(page: str) -> FakeLoginForm:
    """Return the complete credential form or fail with a useful test error."""
    parser = FakeLoginFormParser()
    parser.feed(page)
    if (
        parser.action is None
        or parser.request is None
        or parser.cpf_name is None
        or parser.password_name is None
    ):
        raise ValueError("fake login form is incomplete")
    return FakeLoginForm(
        action=parser.action,
        request=parser.request,
        cpf_name=parser.cpf_name,
        password_name=parser.password_name,
    )


def fixed_clock() -> datetime:
    """Return a stable aware time for launcher integrations."""
    return FIXED_NOW


def route_paths(app: FastAPI) -> set[str]:
    """Return only HTTP paths registered by the application."""
    paths: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        if path := getattr(route, "path", None):
            paths.add(path)
        elif included := getattr(route, "original_router", None):
            pending.extend(included.routes)
    return paths


def end_to_end_settings() -> GovBrRuntimeSettings:
    """Return the explicit embedded consumer/provider launcher profile."""
    return GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_end_to_end=True,
    )


async def complete_fake_flow(
    client: httpx.AsyncClient,
    *,
    cpf: str,
    password: str,
) -> httpx.Response:
    """Drive the three-system flow through its browser-visible redirects."""
    login = await client.get("/auth/govbr/login")
    authorize = await client.get(login.headers["location"])
    form = parse_fake_login_form(authorize.text)
    provider_result = await client.post(
        form.action,
        data={"request": form.request, "cpf": cpf, "password": password},
    )
    if provider_result.status_code != 302:
        return provider_result
    return await client.get(provider_result.headers["location"])


def test_launcher_defaults_to_provider_only(monkeypatch) -> None:
    """The default fake profile must not expose consumer or documentation routes."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")
    monkeypatch.delenv("GOVBR_FAKE_END_TO_END", raising=False)

    app = create_fake_app(clock=fixed_clock)

    assert route_paths(app) == {"/authorize", "/login", "/token", "/userinfo", "/jwk"}
    assert "/" not in route_paths(app)


def test_fake_module_launcher_selects_fake_when_provider_is_absent(monkeypatch) -> None:
    """Invoking the fake module alone must select its provider-only profile."""
    monkeypatch.delenv("GOVBR_PROVIDER", raising=False)

    app = create_fake_app(clock=fixed_clock)

    assert route_paths(app) == {"/authorize", "/login", "/token", "/userinfo", "/jwk"}


@pytest.mark.asyncio
async def test_end_to_end_home_exposes_credentials_and_provider_login_form() -> None:
    """The interactive profile must preserve the current home and credential form."""
    app = create_fake_app(settings=end_to_end_settings(), clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            home = await client.get("/")
            login = await client.get("/auth/govbr/login")
            authorize = await client.get(login.headers["location"])
            form = parse_fake_login_form(authorize.text)

    assert home.status_code == 200
    assert home.headers["cache-control"] == "no-store"
    assert "SIMULAÇÃO LOCAL" in home.text
    assert "Ana Demo" in home.text and "ana-demo" in home.text
    assert login.status_code == 302
    assert authorize.status_code == 200
    assert "Ana Demo" not in authorize.text
    assert "Bruno Demo" not in authorize.text
    assert form.cpf_name == "cpf"
    assert form.password_name == "password"


@pytest.mark.parametrize(
    "cpf,password,name,email,masked_cpf",
    (
        ("12345678901", "ana-demo", "Ana Demo", "ana@example.test", "***.***.***-01"),
        (
            "98765432100",
            "bruno-demo",
            "Bruno Demo",
            "bruno@example.test",
            "***.***.***-00",
        ),
    ),
    ids=("ana", "bruno"),
)
@pytest.mark.asyncio
async def test_end_to_end_completes_credential_flow_without_exposing_secrets(
    cpf: str,
    password: str,
    name: str,
    email: str,
    masked_cpf: str,
) -> None:
    """A valid fake identity must reach the masked consumer success page."""
    app = create_fake_app(settings=end_to_end_settings(), clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            callback = await complete_fake_flow(client, cpf=cpf, password=password)

    assert callback.status_code == 200
    assert callback.headers["cache-control"] == "no-store"
    assert name in callback.text and email in callback.text
    assert masked_cpf in callback.text
    assert password not in callback.text
    assert cpf not in callback.text
    assert all(
        sensitive not in callback.text
        for sensitive in (
            "access_token",
            "id_token",
            "code_verifier",
            "local-fake-only",
        )
    )


@pytest.mark.asyncio
async def test_end_to_end_invalid_credentials_return_generic_401() -> None:
    """Invalid credentials must expose one generic public failure only."""
    app = create_fake_app(settings=end_to_end_settings(), clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            response = await complete_fake_flow(
                client,
                cpf="12345678901",
                password="wrong-password",
            )

    assert response.status_code == 401
    assert "CPF ou senha inválidos." in response.text
    assert "wrong-password" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_end_to_end_uses_json_repository_without_exposing_credentials(
    tmp_path,
    monkeypatch,
) -> None:
    """The launcher environment repository must replace demonstrative users."""
    source = tmp_path / "fake-users.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "11122233344",
                        "password": "json-secret",
                        "name": "Carla JSON",
                        "email": "carla@example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOVBR_FAKE_END_TO_END", "true")
    monkeypatch.setenv("GOVBR_FAKE_USERS_FILE", str(source))
    app = create_fake_app(clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            home = await client.get("/")
            callback = await complete_fake_flow(
                client,
                cpf="11122233344",
                password="json-secret",
            )

    assert callback.status_code == 200
    assert "Carla JSON" in callback.text
    assert "Ana Demo" not in home.text
    assert "Bruno Demo" not in home.text
    assert "ana-demo" not in home.text
    assert "bruno-demo" not in home.text
    assert "json-secret" not in home.text


@pytest.mark.asyncio
async def test_end_to_end_explicit_repository_precedes_environment(
    tmp_path,
    monkeypatch,
) -> None:
    """An explicit caller repository must take precedence over the environment file."""
    source = tmp_path / "environment-users.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "11122233344",
                        "password": "environment-secret",
                        "name": "Environment User",
                        "email": "environment@example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOVBR_FAKE_END_TO_END", "true")
    monkeypatch.setenv("GOVBR_FAKE_USERS_FILE", str(source))
    repository = InMemoryFakeUserRepository(
        (
            (
                FakeUser(
                    sub="55566677788",
                    name="Explicit User",
                    email="explicit@example.test",
                ),
                SecretStr("explicit-secret"),
            ),
        )
    )
    app = create_fake_app(clock=fixed_clock, user_repository=repository)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            home = await client.get("/")
            callback = await complete_fake_flow(
                client,
                cpf="55566677788",
                password="explicit-secret",
            )

    assert callback.status_code == 200
    assert "Explicit User" in callback.text
    assert "Environment User" not in callback.text
    assert "Credenciais da demo" not in home.text
    assert "explicit-secret" not in home.text


@pytest.mark.asyncio
async def test_end_to_end_invalid_callback_returns_fixed_safe_page() -> None:
    """Malformed callbacks must be converted into the stable public boundary page."""
    app = create_fake_app(settings=end_to_end_settings(), clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            response = await client.get("/auth/govbr/callback")

    assert response.status_code == 400
    assert "invalid_callback" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "detail" not in response.text


@pytest.mark.asyncio
async def test_end_to_end_invalid_state_never_exposes_submitted_code() -> None:
    """Typed callback errors must not reflect attacker-controlled codes."""
    app = create_fake_app(settings=end_to_end_settings(), clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            response = await client.get(
                "/auth/govbr/callback",
                params={"code": "unused-code", "state": "invalid-state"},
            )

    assert response.status_code == 400
    assert "invalid_state" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "unused-code" not in response.text


@pytest.mark.asyncio
async def test_end_to_end_internal_error_never_exposes_exception_text(mocker) -> None:
    """Unexpected rendering failures must return a fixed opaque error page."""
    mocker.patch(
        "govbr_auth.fake.fastapi.render_success",
        side_effect=RuntimeError("sensitive internal"),
    )
    app = create_fake_app(settings=end_to_end_settings(), clock=fixed_clock)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as client:
            response = await complete_fake_flow(
                client,
                cpf="12345678901",
                password="ana-demo",
            )

    assert response.status_code == 500
    assert "internal_error" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "sensitive internal" not in response.text


def test_run_uses_validated_loopback_settings(mocker) -> None:
    """The launcher must bind only the validated fixed loopback endpoint."""
    uvicorn_run = mocker.patch("uvicorn.run")
    from govbr_auth.fake import run

    run()

    uvicorn_run.assert_called_once_with(
        "govbr_auth.fake:create_fake_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


def test_fake_module_executes_run(mocker) -> None:
    """Module execution must delegate once to the public launcher."""
    run = mocker.patch("govbr_auth.fake.run")

    runpy.run_module("govbr_auth.fake.__main__", run_name="__main__")

    run.assert_called_once_with()
