"""Exercise the installable local authentication showcase end to end."""

import json
import runpy
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

import httpx
import pytest

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolate_demo_user_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOVBR_FAKE_USERS_FILE", raising=False)


@dataclass(frozen=True, slots=True)
class FakeLoginForm:
    action: str
    request: str
    cpf_name: str
    password_name: str


class FakeLoginFormParser(HTMLParser):
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


async def complete_demo_flow(
    client: httpx.AsyncClient, *, cpf: str, password: str
) -> httpx.Response:
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


@pytest.mark.asyncio
async def test_demo_home_exposes_credentials_and_provider_login_form() -> None:
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            follow_redirects=False,
        ) as client:
            home = await client.get("/")
            login = await client.get("/auth/govbr/login")
            authorize = await client.get(login.headers["location"])
            form = parse_fake_login_form(authorize.text)

    assert home.status_code == 200
    assert "SIMULAÇÃO LOCAL" in home.text
    assert "Ana Demo" in home.text and "ana-demo" in home.text
    assert login.status_code == 302
    assert authorize.status_code == 200
    assert "Ana Demo" not in authorize.text
    assert "Bruno Demo" not in authorize.text
    assert form.cpf_name == "cpf"
    assert form.password_name == "password"


@pytest.mark.parametrize(
    "cpf,password,name,email",
    (
        ("12345678901", "ana-demo", "Ana Demo", "ana@example.test"),
        ("98765432100", "bruno-demo", "Bruno Demo", "bruno@example.test"),
    ),
    ids=("ana", "bruno"),
)
@pytest.mark.asyncio
async def test_demo_completes_credential_flow(
    cpf: str,
    password: str,
    name: str,
    email: str,
) -> None:
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            follow_redirects=False,
        ) as client:
            callback = await complete_demo_flow(
                client,
                cpf=cpf,
                password=password,
            )

    assert callback.status_code == 200
    assert name in callback.text and email in callback.text
    assert password not in callback.text
    assert cpf not in callback.text
    assert all(
        sensitive not in callback.text
        for sensitive in (
            "access_token",
            "id_token",
            "code_verifier",
            "local-demo-only",
        )
    )


@pytest.mark.asyncio
async def test_demo_invalid_credentials_return_401() -> None:
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            follow_redirects=False,
        ) as client:
            response = await complete_demo_flow(
                client,
                cpf="12345678901",
                password="wrong-password",
            )

    assert response.status_code == 401
    assert "CPF ou senha inválidos." in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_demo_uses_json_repository_without_exposing_credentials(
    tmp_path,
    monkeypatch,
) -> None:
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
    monkeypatch.setenv("GOVBR_FAKE_USERS_FILE", str(source))
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            follow_redirects=False,
        ) as client:
            home = await client.get("/")
            callback = await complete_demo_flow(
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
async def test_demo_explicit_repository_precedes_environment(
    tmp_path,
    monkeypatch,
) -> None:
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
    monkeypatch.setenv("GOVBR_FAKE_USERS_FILE", str(source))
    from pydantic import SecretStr

    from govbr_auth.demo import create_demo_app
    from govbr_auth.fake import FakeUser, InMemoryFakeUserRepository

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
    app = create_demo_app(
        clock=lambda: FIXED_NOW,
        user_repository=repository,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            follow_redirects=False,
        ) as client:
            home = await client.get("/")
            callback = await complete_demo_flow(
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
async def test_demo_invalid_callback_returns_fixed_safe_page() -> None:
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
        ) as client:
            response = await client.get("/auth/govbr/callback")

    assert response.status_code == 400
    assert "invalid_callback" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "detail" not in response.text


@pytest.mark.asyncio
async def test_demo_invalid_state_returns_typed_auth_error_page() -> None:
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
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
async def test_demo_internal_error_returns_fixed_page_without_exception_text(
    mocker,
) -> None:
    mocker.patch(
        "govbr_auth.demo.render_success",
        side_effect=RuntimeError("sensitive internal"),
    )
    from govbr_auth.demo import create_demo_app

    app = create_demo_app(clock=lambda: FIXED_NOW)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app,
                raise_app_exceptions=False,
            ),
            base_url="http://localhost",
            follow_redirects=False,
        ) as client:
            response = await complete_demo_flow(
                client,
                cpf="12345678901",
                password="ana-demo",
            )

    assert response.status_code == 500
    assert "internal_error" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "sensitive internal" not in response.text


def test_demo_run_binds_only_the_fixed_ipv4_loopback(mocker) -> None:
    uvicorn_run = mocker.patch("uvicorn.run")
    from govbr_auth.demo import run

    run()

    uvicorn_run.assert_called_once_with(
        "govbr_auth.demo:create_demo_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


def test_demo_module_executes_run(mocker) -> None:
    run = mocker.patch("govbr_auth.demo.run")

    runpy.run_module("govbr_auth.demo.__main__", run_name="__main__")

    run.assert_called_once_with()
