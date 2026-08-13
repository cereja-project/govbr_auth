"""Exercise the installable local authentication showcase end to end."""

import runpy
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

import httpx
import pytest

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FakeLoginForm:
    action: str
    request: str
    subjects: tuple[str, ...]


class FakeLoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.request: str | None = None
        self.subjects: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "form":
            self.action = values.get("action")
        elif tag == "input" and values.get("name") == "request":
            self.request = values.get("value")
        elif tag == "button" and values.get("name") == "subject":
            subject = values.get("value")
            if subject is not None:
                self.subjects.append(subject)


def parse_fake_login_form(page: str) -> FakeLoginForm:
    parser = FakeLoginFormParser()
    parser.feed(page)
    if parser.action is None or parser.request is None:
        raise ValueError("fake login form is incomplete")
    return FakeLoginForm(
        action=parser.action,
        request=parser.request,
        subjects=tuple(parser.subjects),
    )


async def complete_demo_flow(
    client: httpx.AsyncClient,
    *,
    subject: str,
) -> httpx.Response:
    login = await client.get("/auth/govbr/login")
    authorize = await client.get(login.headers["location"])
    form = parse_fake_login_form(authorize.text)
    provider_result = await client.post(
        form.action,
        data={"request": form.request, "subject": subject},
    )
    return await client.get(provider_result.headers["location"])


@pytest.mark.asyncio
async def test_demo_home_exposes_guided_flow_and_interactive_provider() -> None:
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
    assert "FAKE / SIMULAÇÃO" in home.text
    assert login.status_code == 302
    assert authorize.status_code == 200
    assert "Ana Demo" in authorize.text
    assert "Bruno Demo" in authorize.text
    assert form.subjects == ("demo-ana", "demo-bruno")


@pytest.mark.parametrize(
    "subject,name,email",
    (
        ("demo-ana", "Ana Demo", "ana@example.test"),
        ("demo-bruno", "Bruno Demo", "bruno@example.test"),
    ),
    ids=("ana", "bruno"),
)
@pytest.mark.asyncio
async def test_demo_completes_repeatable_sanitized_interactive_flow(
    subject: str,
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
            first_callback = await complete_demo_flow(client, subject=subject)
            second_callback = await complete_demo_flow(client, subject=subject)

    assert first_callback.status_code == 200
    assert all(value in first_callback.text for value in (name, subject, email))
    assert second_callback.status_code == 200
    assert all(value in second_callback.text for value in (name, subject, email))
    assert all(
        sensitive not in first_callback.text + second_callback.text
        for sensitive in (
            "access_token",
            "id_token",
            "code_verifier",
            "local-demo-only",
        )
    )


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
            response = await complete_demo_flow(client, subject="demo-ana")

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
