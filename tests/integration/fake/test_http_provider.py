"""HTTP integration tests for the explicit Fake Gov.br FastAPI factories."""

import base64
import hashlib
import html
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

import govbr_auth
from govbr_auth import fake
from govbr_auth.fake import (
    FakeClient,
    FakeGovBrProvider,
    FakeGovBrSettings,
    FakeSigningKey,
    FakeUser,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
)
from govbr_auth.fake.fastapi import create_fake_govbr_app, create_fake_govbr_router

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
VERIFIER = "http-provider-pkce-verifier-abcdefghijklmnopqrstuvwxyz0123456789"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode("ascii")).digest())
    .rstrip(b"=")
    .decode("ascii")
)


class LoginFormParser(HTMLParser):
    """Extract the opaque request and selectable subjects from fake login HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.request_artifact: str | None = None
        self.subjects: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "form":
            self.action = attributes.get("action")
        if tag == "input" and attributes.get("name") == "request":
            self.request_artifact = attributes.get("value")
        if tag == "button" and attributes.get("name") == "subject":
            subject = attributes.get("value")
            if subject is not None:
                self.subjects.append(subject)


def provider_factory(*, user: FakeUser | None = None) -> FakeGovBrProvider:
    """Build a provider with real Fernet artifacts, RSA signing, and memory stores."""
    configured_user = user or FakeUser(
        sub="12345678900",
        name="Maria da Silva",
        email="maria@example.test",
        email_verified=True,
    )
    settings = FakeGovBrSettings(
        base_url="http://localhost/",
        issuer="http://localhost/",
        artifact_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id="client-123",
                client_secret=SecretStr("client-secret-marker"),
                registered_redirect_uris=("http://localhost/callback",),
            ),
        ),
    )
    return FakeGovBrProvider(
        settings=settings,
        user_store=InMemoryFakeUserStore((configured_user,)),
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=FakeSigningKey.generate(kid="fake-provider-key"),
    )


def authorization_params(**overrides: str) -> dict[str, str]:
    """Return a valid literal OAuth authorization query with optional overrides."""
    values = {
        "response_type": "code",
        "client_id": "client-123",
        "redirect_uri": "http://localhost/callback",
        "scope": "openid profile email",
        "state": "state-123",
        "nonce": "nonce-123",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    values.update(overrides)
    return values


def parse_login_form(document: str) -> LoginFormParser:
    """Parse the fake login form without depending on implementation markup."""
    parser = LoginFormParser()
    parser.feed(document)
    return parser


def oauth_values(location: str) -> dict[str, list[str]]:
    """Return decoded OAuth query values from a redirect location."""
    return parse_qs(urlsplit(location).query)


def provider_route_paths(application: object) -> set[str]:
    """Return only the five fake-provider paths from an ASGI router or app."""
    paths: set[str] = set()
    pending = list(application.routes)
    while pending:
        route = pending.pop()
        path = getattr(route, "path", "")
        if path.endswith(("/authorize", "/login", "/token", "/jwk", "/userinfo")):
            paths.add(path)
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            pending.extend(included_router.routes)
    return paths


def test_fake_fastapi_module_exposes_explicit_factories() -> None:
    assert callable(create_fake_govbr_app)
    assert callable(create_fake_govbr_router)
    assert "create_fake_govbr_app" in fake.__all__
    assert "create_fake_govbr_router" in fake.__all__
    assert not hasattr(govbr_auth, "create_fake_govbr_app")
    assert not hasattr(govbr_auth, "create_fake_govbr_router")


def test_factories_expose_exact_provider_routes_only_after_explicit_calls() -> None:
    provider = provider_factory()

    router = create_fake_govbr_router(provider, prefix="/local-provider")
    application = create_fake_govbr_app(provider)

    assert provider_route_paths(router) == {
        "/local-provider/authorize",
        "/local-provider/login",
        "/local-provider/token",
        "/local-provider/jwk",
        "/local-provider/userinfo",
    }
    assert provider_route_paths(application) == {
        "/authorize",
        "/login",
        "/token",
        "/jwk",
        "/userinfo",
    }


@pytest.mark.asyncio
async def test_mounted_router_completes_http_flow_with_prefix_and_root_path() -> None:
    from fastapi import FastAPI

    provider = provider_factory()
    application = FastAPI(root_path="/gateway")
    application.include_router(
        create_fake_govbr_router(
            provider,
            prefix="/local-provider",
            clock=lambda: FIXED_NOW,
        )
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, root_path="/gateway"),
        base_url="http://localhost/gateway",
    ) as http:
        authorize_response = await http.get(
            "/local-provider/authorize",
            params=authorization_params(),
        )
        login_form = parse_login_form(authorize_response.text)
        login_response = await http.post(
            login_form.action.removeprefix("/gateway"),
            data={
                "request": login_form.request_artifact,
                "subject": "12345678900",
            },
        )
        redirect_values = oauth_values(login_response.headers["location"])
        token_response = await http.post(
            "/local-provider/token",
            auth=("client-123", "client-secret-marker"),
            data={
                "grant_type": "authorization_code",
                "code": redirect_values["code"][0],
                "redirect_uri": "http://localhost/callback",
                "code_verifier": VERIFIER,
            },
        )

    assert authorize_response.status_code == 200
    assert login_form.action == "/gateway/local-provider/login"
    assert login_response.status_code == 302
    assert redirect_values["state"] == ["state-123"]
    assert token_response.status_code == 200
    assert token_response.json()["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_second_mounted_router_posts_authorization_to_its_own_provider() -> None:
    from fastapi import FastAPI

    first_provider = provider_factory()
    second_provider = provider_factory()
    application = FastAPI(root_path="/gateway")
    application.include_router(
        create_fake_govbr_router(
            first_provider,
            prefix="/first-provider",
            clock=lambda: FIXED_NOW,
        )
    )
    application.include_router(
        create_fake_govbr_router(
            second_provider,
            prefix="/second-provider",
            clock=lambda: FIXED_NOW,
        )
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, root_path="/gateway"),
        base_url="http://localhost/gateway",
    ) as http:
        authorize_response = await http.get(
            "/second-provider/authorize",
            params=authorization_params(),
        )
        login_form = parse_login_form(authorize_response.text)
        login_response = await http.post(
            login_form.action.removeprefix("/gateway"),
            data={
                "request": login_form.request_artifact,
                "subject": "12345678900",
            },
        )

    assert authorize_response.status_code == 200
    assert login_form.action == "/gateway/second-provider/login"
    assert login_response.status_code == 302
    assert oauth_values(login_response.headers["location"])["state"] == ["state-123"]


@pytest.mark.asyncio
async def test_interactive_authorize_escapes_user_values_and_never_renders_secret() -> (
    None
):
    malicious_subject = 'subject-<svg onload="alert(1)">'
    malicious_name = 'Maria <img src=x onerror="alert(2)"> & "Teste"'
    user = FakeUser(
        sub=malicious_subject,
        name=malicious_name,
        email="maria@example.test",
    )
    application = create_fake_govbr_app(
        provider_factory(user=user), clock=lambda: FIXED_NOW
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        response = await http.get("/authorize", params=authorization_params())

    login_form = parse_login_form(response.text)
    assert response.status_code == 200
    assert "FAKE / SIMULAÇÃO" in response.text
    assert html.escape(malicious_name, quote=True) in response.text
    assert html.escape(malicious_subject, quote=True) in response.text
    assert malicious_name not in response.text
    assert malicious_subject not in response.text
    assert "client-secret-marker" not in response.text
    assert login_form.request_artifact is not None
    assert login_form.subjects == [user.sub]


@pytest.mark.asyncio
async def test_interactive_flow_returns_exact_oauth_and_userinfo_contract() -> None:
    provider = provider_factory()
    application = create_fake_govbr_app(provider, clock=lambda: FIXED_NOW)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        authorize_response = await http.get("/authorize", params=authorization_params())
        login_form = parse_login_form(authorize_response.text)
        login_response = await http.post(
            "/login",
            data={
                "request": login_form.request_artifact,
                "subject": "12345678900",
            },
        )
        redirect_values = oauth_values(login_response.headers["location"])
        token_response = await http.post(
            "/token",
            auth=("client-123", "client-secret-marker"),
            data={
                "grant_type": "authorization_code",
                "code": redirect_values["code"][0],
                "redirect_uri": "http://localhost/callback",
                "code_verifier": VERIFIER,
            },
        )
        jwks_response = await http.get("/jwk")
        userinfo_response = await http.get(
            "/userinfo",
            headers={
                "Authorization": f"Bearer {token_response.json()['access_token']}"
            },
        )

    token_payload = token_response.json()
    jwks_payload = jwks_response.json()
    assert authorize_response.status_code == 200
    assert login_response.status_code == 302
    assert redirect_values["state"] == ["state-123"]
    assert token_response.status_code == 200
    assert set(token_payload) == {
        "access_token",
        "token_type",
        "expires_in",
        "id_token",
        "scope",
    }
    assert token_payload["token_type"] == "Bearer"
    assert token_payload["expires_in"] == 600
    assert token_payload["scope"] == "openid profile email"
    assert jwks_response.status_code == 200
    assert jwks_payload["keys"][0]["alg"] == "RS256"
    assert {"d", "p", "q", "dp", "dq", "qi"}.isdisjoint(jwks_payload["keys"][0])
    assert userinfo_response.status_code == 200
    assert userinfo_response.json() == {
        "sub": "12345678900",
        "name": "Maria da Silva",
        "email": "maria@example.test",
        "email_verified": True,
    }


@pytest.mark.asyncio
async def test_automatic_flow_returns_same_oauth_and_userinfo_contract() -> None:
    provider = provider_factory()
    application = create_fake_govbr_app(
        provider,
        automatic_subject="12345678900",
        clock=lambda: FIXED_NOW,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        authorize_response = await http.get("/authorize", params=authorization_params())
        redirect_values = oauth_values(authorize_response.headers["location"])
        token_response = await http.post(
            "/token",
            auth=("client-123", "client-secret-marker"),
            data={
                "grant_type": "authorization_code",
                "code": redirect_values["code"][0],
                "redirect_uri": "http://localhost/callback",
                "code_verifier": VERIFIER,
            },
        )
        userinfo_response = await http.get(
            "/userinfo",
            headers={
                "Authorization": f"Bearer {token_response.json()['access_token']}"
            },
        )

    assert authorize_response.status_code == 302
    assert redirect_values["state"] == ["state-123"]
    assert set(token_response.json()) == {
        "access_token",
        "token_type",
        "expires_in",
        "id_token",
        "scope",
    }
    assert token_response.json()["token_type"] == "Bearer"
    assert userinfo_response.json() == {
        "sub": "12345678900",
        "name": "Maria da Silva",
        "email": "maria@example.test",
        "email_verified": True,
    }


@pytest.mark.parametrize(
    "authorization",
    [
        pytest.param(None, id="missing"),
        pytest.param("Digest abc", id="wrong_scheme"),
        pytest.param("Basic !!!", id="invalid_base64"),
        pytest.param(
            f"Basic {base64.b64encode(b'without-colon').decode('ascii')}",
            id="missing_colon",
        ),
        pytest.param(
            f"Basic {base64.b64encode(b':secret').decode('ascii')}",
            id="blank_client",
        ),
        pytest.param(
            f"Basic {base64.b64encode(b'client:').decode('ascii')}",
            id="blank_secret",
        ),
    ],
)
@pytest.mark.asyncio
async def test_token_rejects_malformed_basic_without_echoing_header(
    authorization: str | None,
) -> None:
    application = create_fake_govbr_app(provider_factory(), clock=lambda: FIXED_NOW)
    headers = {} if authorization is None else {"Authorization": authorization}
    sensitive_header = authorization or "absent-basic-header-marker"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        response = await http.post(
            "/token",
            headers=headers,
            data={
                "grant_type": "authorization_code",
                "code": "sensitive-code-marker",
                "redirect_uri": "http://localhost/callback",
                "code_verifier": "sensitive-verifier-marker",
            },
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_client",
        "error_description": "Client authentication failed.",
    }
    assert "sensitive-code-marker" not in response.text
    assert "sensitive-verifier-marker" not in response.text
    assert sensitive_header not in response.text


@pytest.mark.parametrize(
    "authorization",
    [
        pytest.param(None, id="missing"),
        pytest.param("Basic abc", id="wrong_scheme"),
        pytest.param("Bearer", id="missing_token"),
        pytest.param("Bearer   ", id="blank_token"),
        pytest.param("Bearer token with spaces", id="embedded_spaces"),
    ],
)
@pytest.mark.asyncio
async def test_userinfo_rejects_malformed_bearer_without_echoing_header(
    authorization: str | None,
) -> None:
    application = create_fake_govbr_app(provider_factory(), clock=lambda: FIXED_NOW)
    headers = {} if authorization is None else {"Authorization": authorization}
    sensitive_header = authorization or "absent-bearer-header-marker"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        response = await http.get("/userinfo", headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_token",
        "error_description": "The access token is invalid or expired.",
    }
    assert sensitive_header not in response.text


@pytest.mark.asyncio
async def test_missing_query_fields_return_safe_invalid_request() -> None:
    application = create_fake_govbr_app(provider_factory(), clock=lambda: FIXED_NOW)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        query_response = await http.get(
            "/authorize",
            params={"state": "sensitive-state-marker"},
        )

    expected = {
        "error": "invalid_request",
        "error_description": "The authorization request is invalid.",
    }
    assert query_response.status_code == 400
    assert query_response.json() == expected
    assert "sensitive-state-marker" not in query_response.text


@pytest.mark.asyncio
async def test_missing_form_fields_return_safe_invalid_request() -> None:
    application = create_fake_govbr_app(provider_factory(), clock=lambda: FIXED_NOW)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        form_response = await http.post(
            "/login",
            data={"subject": "sensitive-subject-marker"},
        )

    expected = {
        "error": "invalid_request",
        "error_description": "The authorization request is invalid.",
    }
    assert form_response.status_code == 400
    assert form_response.json() == expected
    assert "sensitive-subject-marker" not in form_response.text


@pytest.mark.asyncio
async def test_authorize_provider_error_keeps_oauth_status_and_removes_values() -> None:
    application = create_fake_govbr_app(provider_factory(), clock=lambda: FIXED_NOW)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        invalid_scope_response = await http.get(
            "/authorize",
            params=authorization_params(
                scope="profile sensitive-scope-marker",
                state="sensitive-state-marker",
            ),
        )

    assert invalid_scope_response.status_code == 400
    assert invalid_scope_response.json() == {
        "error": "invalid_scope",
        "error_description": "The requested scope is invalid.",
    }
    assert "sensitive-scope-marker" not in invalid_scope_response.text
    assert "sensitive-state-marker" not in invalid_scope_response.text


@pytest.mark.asyncio
async def test_token_provider_error_keeps_oauth_status_and_removes_values() -> None:
    application = create_fake_govbr_app(provider_factory(), clock=lambda: FIXED_NOW)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost",
    ) as http:
        invalid_client_response = await http.post(
            "/token",
            auth=("client-123", "sensitive-wrong-secret"),
            data={
                "grant_type": "authorization_code",
                "code": "sensitive-code-marker",
                "redirect_uri": "http://localhost/callback",
                "code_verifier": "sensitive-verifier-marker",
            },
        )

    assert invalid_client_response.status_code == 401
    assert invalid_client_response.json() == {
        "error": "invalid_client",
        "error_description": "Client authentication failed.",
    }
    assert "sensitive-wrong-secret" not in invalid_client_response.text
    assert "sensitive-code-marker" not in invalid_client_response.text
    assert "sensitive-verifier-marker" not in invalid_client_response.text
