"""End-to-end FastAPI authentication against interchangeable local providers."""

import asyncio
import json
import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import SecretStr
from starlette.requests import Request
from starlette.types import Receive, Scope, Send

import govbr_auth
from govbr_auth.core import (
    GovBrClient,
    GovBrSettings,
    IdTokenValidator,
    EncryptedTransactionCodec,
    ProviderEnvironment,
)
from govbr_auth.fake import (
    FakeClient,
    FakeGovBrProvider,
    FakeGovBrSettings,
    FakeSigningKey,
    FakeTokenIssuer,
    FakeUser,
    InMemoryAuthorizationCodeReplayStore,
    InMemoryFakeUserStore,
    create_fake_govbr_app,
)
from govbr_auth.fastapi import (
    AuthContext,
    GovBrAuth,
    create_govbr_router,
)
from govbr_auth.runtime import GovBrProvider, GovBrRuntime, GovBrRuntimeSettings
from tests.integration.core.provider import GovBrAsgiProvider

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
PROVIDER_BASE_URL = "http://127.0.0.1"
CONSUMER_BASE_URL = "http://localhost"
CALLBACK_URL = f"{CONSUMER_BASE_URL}/auth/govbr/callback"
SUBJECT = "12345678900"
_clock_value: ContextVar[datetime] = ContextVar(
    "fastapi_integration_clock",
    default=FIXED_NOW,
)
_PROTECTED_ID_TOKEN_CLAIMS = frozenset(
    {"alg", "aud", "exp", "iat", "iss", "kid", "nonce", "sub", "typ"}
)


def fixed_clock() -> datetime:
    """Return the task-local deterministic integration-test time."""
    return _clock_value.get()


def build_runtime(
    settings: GovBrSettings,
    transport: httpx.AsyncBaseTransport,
) -> GovBrRuntime:
    """Build a real runtime over the selected provider transport."""
    http = httpx.AsyncClient(transport=transport)
    client = GovBrClient(
        settings,
        EncryptedTransactionCodec(settings.transaction_secret),
        IdTokenValidator(settings=settings),
        http,
    )
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.OFFICIAL,
            oauth=settings,
        ),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=http,
    )


def build_consumer(
    settings: GovBrSettings,
    transport: httpx.AsyncBaseTransport,
) -> FastAPI:
    """Build one consumer application independent of provider implementation."""
    app = FastAPI()
    app.state.received_contexts = []
    runtime = build_runtime(settings, transport)

    async def on_success(context: AuthContext) -> Response:
        app.state.received_contexts.append(context)
        return JSONResponse({"sub": context.user.subject})

    auth = GovBrAuth(runtime=runtime, on_success=on_success, clock=fixed_clock)
    app.include_router(auth.router)
    return app


@dataclass(slots=True)
class ProviderFaults:
    """Control provider-boundary failures without replacing consumer code."""

    nonce_override: str | None = None
    invalid_signature: bool = False
    substituted_subject: str | None = None
    timeout_token_request: bool = False


TokenSigner = Callable[[Mapping[str, object]], str]


class ProviderTransport(httpx.AsyncBaseTransport):
    """Run a real ASGI provider and inject protocol-level failure responses."""

    def __init__(
        self,
        *,
        application: object,
        faults: ProviderFaults,
        token_signer: TokenSigner,
        attacker_signer: TokenSigner,
    ) -> None:
        self._transport = httpx.ASGITransport(app=application)
        self._faults = faults
        self._token_signer = token_signer
        self._attacker_signer = attacker_signer

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Dispatch a request and alter only explicitly selected provider outputs."""
        if self._faults.timeout_token_request and request.url.path == "/token":
            raise httpx.ReadTimeout("simulated provider timeout", request=request)

        response = await self._transport.handle_async_request(request)
        if request.url.path == "/token" and response.is_success:
            return await self._token_response(response, request=request)
        if request.url.path == "/userinfo" and response.is_success:
            return await self._userinfo_response(response, request=request)
        return response

    async def aclose(self) -> None:
        """Close the wrapped in-process ASGI transport."""
        await self._transport.aclose()

    async def _token_response(
        self,
        response: httpx.Response,
        *,
        request: httpx.Request,
    ) -> httpx.Response:
        await response.aread()
        payload = response.json()
        if self._faults.nonce_override is None and not self._faults.invalid_signature:
            return response

        claims = jwt.decode(
            payload["id_token"],
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
        if self._faults.nonce_override is not None:
            claims["nonce"] = self._faults.nonce_override
        signer = (
            self._attacker_signer
            if self._faults.invalid_signature
            else self._token_signer
        )
        payload["id_token"] = signer(claims)
        return _json_response(response, request=request, payload=payload)

    async def _userinfo_response(
        self,
        response: httpx.Response,
        *,
        request: httpx.Request,
    ) -> httpx.Response:
        if self._faults.substituted_subject is None:
            return response

        await response.aread()
        payload = response.json()
        payload["sub"] = self._faults.substituted_subject
        return _json_response(response, request=request, payload=payload)


class OfficialCompatibleAuthorizationApp:
    """Add a browser authorization endpoint to the strict official-like provider."""

    def __init__(self, provider: GovBrAsgiProvider) -> None:
        self._provider = provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve authorization or delegate token, JWKS, and userinfo exchanges."""
        if scope["type"] != "http" or scope["path"] != "/authorize":
            await self._provider(scope, receive, send)
            return

        request = Request(scope, receive)
        code = self._provider.authorize(str(request.url))
        state = request.query_params["state"]
        response = RedirectResponse(
            _append_query(CALLBACK_URL, code=code, state=state),
            status_code=302,
        )
        await response(scope, receive, send)


@dataclass(frozen=True, slots=True)
class ProviderVariant:
    """Carry only provider configuration, transport, and test fault controls."""

    settings: GovBrSettings
    transport: ProviderTransport
    faults: ProviderFaults


@dataclass(frozen=True, slots=True)
class BrowserFlowResult:
    """Capture the observable redirects and final consumer response."""

    authorization_location: str
    callback_location: str
    response: httpx.Response


class OAuthBrowser:
    """Follow the same browser-visible redirect flow for either provider."""

    def __init__(
        self,
        *,
        consumer_http: httpx.AsyncClient,
        provider_http: httpx.AsyncClient,
        received_contexts: list[AuthContext],
    ) -> None:
        self._consumer_http = consumer_http
        self._provider_http = provider_http
        self.received_contexts = received_contexts

    async def authorize(self) -> tuple[str, str]:
        """Follow login to the provider and return both redirect locations."""
        login_response = await self._consumer_http.get("/auth/govbr/login")
        authorization_location = login_response.headers["location"]
        provider_response = await self._provider_http.get(authorization_location)
        return authorization_location, provider_response.headers["location"]

    async def callback(self, callback_location: str) -> httpx.Response:
        """Send the provider callback redirect to the consumer application."""
        parsed = urlsplit(callback_location)
        path = urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
        return await self._consumer_http.get(path)

    async def authenticate(self) -> BrowserFlowResult:
        """Complete the browser redirect flow and return all observable results."""
        authorization_location, callback_location = await self.authorize()
        response = await self.callback(callback_location)
        return BrowserFlowResult(
            authorization_location=authorization_location,
            callback_location=callback_location,
            response=response,
        )


def _append_query(url: str, **values: str) -> str:
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    for name, value in values.items():
        query[name] = [value]
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, doseq=True),
            parts.fragment,
        )
    )


def _path(location: str) -> str:
    parsed = urlsplit(location)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _json_response(
    response: httpx.Response,
    *,
    request: httpx.Request,
    payload: Mapping[str, object],
) -> httpx.Response:
    headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() != "content-length"
    }
    return httpx.Response(
        response.status_code,
        headers=headers,
        content=json.dumps(payload).encode("utf-8"),
        request=request,
    )


def _fake_token_signer(signing_key: FakeSigningKey, issuer: str) -> TokenSigner:
    token_issuer = FakeTokenIssuer(signing_key=signing_key, issuer=issuer)

    def sign(claims: Mapping[str, object]) -> str:
        additional_claims = {
            name: value
            for name, value in claims.items()
            if name not in _PROTECTED_ID_TOKEN_CLAIMS
        }
        token = token_issuer.issue_id_token(
            subject=str(claims["sub"]),
            audience=str(claims["aud"]),
            nonce=str(claims["nonce"]),
            issued_at=datetime.fromtimestamp(int(claims["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
            claims=additional_claims,
        )
        return token.get_secret_value()

    return sign


def _official_token_signer(
    signing_key: rsa.RSAPrivateKey,
    *,
    key_id: str,
) -> TokenSigner:
    def sign(claims: Mapping[str, object]) -> str:
        return jwt.encode(
            dict(claims),
            signing_key,
            algorithm="RS256",
            headers={"kid": key_id},
        )

    return sign


def _consumer_settings(
    *,
    client_id: str,
    client_secret: str,
    issuer: str,
) -> GovBrSettings:
    return GovBrSettings(
        environment=ProviderEnvironment.LOCAL,
        authorization_url=f"{PROVIDER_BASE_URL}/authorize",
        token_url=f"{PROVIDER_BASE_URL}/token",
        userinfo_url=f"{PROVIDER_BASE_URL}/userinfo",
        client_id=client_id,
        client_secret=SecretStr(client_secret),
        redirect_uri=CALLBACK_URL,
        transaction_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        issuer=issuer,
        jwks_url=f"{PROVIDER_BASE_URL}/jwk",
        connect_timeout_seconds=0.1,
        read_timeout_seconds=0.1,
        clock_skew_seconds=0,
    )


def _fake_variant() -> ProviderVariant:
    client_id = "fastapi-client"
    client_secret = "fastapi-client-secret"
    issuer = f"{PROVIDER_BASE_URL}/"
    signing_key = FakeSigningKey.generate(kid="fake-fastapi-key")
    attacker_key = FakeSigningKey.generate(kid="fake-fastapi-key")
    provider_settings = FakeGovBrSettings(
        base_url=issuer,
        issuer=issuer,
        artifact_secret=SecretStr(Fernet.generate_key().decode("ascii")),
        request_ttl_seconds=300,
        authorization_code_ttl_seconds=60,
        access_token_ttl_seconds=600,
        id_token_ttl_seconds=300,
        clients=(
            FakeClient(
                client_id=client_id,
                client_secret=SecretStr(client_secret),
                registered_redirect_uris=(CALLBACK_URL,),
            ),
        ),
    )
    provider = FakeGovBrProvider(
        settings=provider_settings,
        user_store=InMemoryFakeUserStore(
            (
                FakeUser(
                    sub=SUBJECT,
                    name="FastAPI Integration User",
                    email="integration@example.test",
                    email_verified=True,
                ),
            )
        ),
        replay_store=InMemoryAuthorizationCodeReplayStore(),
        signing_key=signing_key,
    )
    faults = ProviderFaults()
    transport = ProviderTransport(
        application=create_fake_govbr_app(
            provider,
            automatic_subject=SUBJECT,
            clock=fixed_clock,
        ),
        faults=faults,
        token_signer=_fake_token_signer(signing_key, issuer),
        attacker_signer=_fake_token_signer(attacker_key, issuer),
    )
    return ProviderVariant(
        settings=_consumer_settings(
            client_id=client_id,
            client_secret=client_secret,
            issuer=issuer,
        ),
        transport=transport,
        faults=faults,
    )


def _official_variant() -> ProviderVariant:
    client_id = "fastapi-client"
    client_secret = "fastapi-client-secret"
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    provider = GovBrAsgiProvider(
        signing_key=signing_key,
        now=FIXED_NOW,
        base_url=PROVIDER_BASE_URL,
        client_id=client_id,
        client_secret=client_secret,
    )
    provider.redirect_uri = CALLBACK_URL
    faults = ProviderFaults()
    transport = ProviderTransport(
        application=OfficialCompatibleAuthorizationApp(provider),
        faults=faults,
        token_signer=_official_token_signer(signing_key, key_id="integration-rsa-key"),
        attacker_signer=_official_token_signer(
            attacker_key,
            key_id="integration-rsa-key",
        ),
    )
    return ProviderVariant(
        settings=_consumer_settings(
            client_id=client_id,
            client_secret=client_secret,
            issuer=provider.issuer,
        ),
        transport=transport,
        faults=faults,
    )


@pytest.fixture(
    params=("fake", "official-compatible-asgi"),
    ids=("fake", "official-compatible-asgi"),
)
def provider_variant(request: pytest.FixtureRequest) -> ProviderVariant:
    """Build function-scoped provider configuration and real ASGI transport."""
    if request.param == "fake":
        return _fake_variant()
    return _official_variant()


@pytest_asyncio.fixture
async def browser(provider_variant: ProviderVariant):
    consumer = build_consumer(provider_variant.settings, provider_variant.transport)
    async with consumer.router.lifespan_context(consumer):
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=consumer),
                base_url=CONSUMER_BASE_URL,
                follow_redirects=False,
            ) as consumer_http,
            httpx.AsyncClient(
                transport=provider_variant.transport,
                base_url=PROVIDER_BASE_URL,
                follow_redirects=False,
            ) as provider_http,
        ):
            yield OAuthBrowser(
                consumer_http=consumer_http,
                provider_http=provider_http,
                received_contexts=consumer.state.received_contexts,
            )


def test_supported_public_api_exports_fastapi_without_fake_factories() -> None:
    assert not hasattr(govbr_auth, "AuthContext")
    assert not hasattr(govbr_auth, "AuthSuccessHandler")
    assert not hasattr(govbr_auth, "GovBrAuth")
    assert not hasattr(govbr_auth, "create_govbr_router")
    assert callable(GovBrAuth)
    assert callable(create_govbr_router)
    assert not hasattr(govbr_auth, "create_fake_govbr_app")
    assert not hasattr(govbr_auth, "create_fake_govbr_router")


@pytest.mark.asyncio
async def test_fake_provider_environment_mounts_consumer_and_provider_on_same_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from govbr_auth.fastapi import GovBrAuth

    monkeypatch.setenv("GOVBR_PROVIDER", "fake")
    for name in (
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    async def on_success(context: AuthContext) -> Response:
        return Response(status_code=204)

    auth = GovBrAuth(on_success=on_success, clock=fixed_clock)
    app = FastAPI()
    app.include_router(auth.router)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            follow_redirects=False,
        ) as http:
            consumer_login = await http.get("/auth/govbr/login")
            provider_authorize = await http.get("/fake-govbr/authorize")

    assert consumer_login.status_code == 302
    assert consumer_login.headers["location"].startswith(
        "http://127.0.0.1:8000/fake-govbr/authorize?"
    )
    assert provider_authorize.status_code == 400
    assert provider_authorize.json()["error"] == "invalid_request"


@pytest.mark.asyncio
async def test_fake_provider_environment_uses_simulator_http_application_for_full_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import govbr_auth.fake.http.routes as fastapi_routes
    from govbr_auth.fastapi import GovBrAuth

    def fail_if_routes_resolve_application(*args, **kwargs):
        del args, kwargs
        raise AssertionError("fake routes must receive the simulator HTTP facade")

    monkeypatch.setattr(
        fastapi_routes,
        "resolve_fake_http_application",
        fail_if_routes_resolve_application,
    )
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")
    for name in (
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    received: list[str] = []

    async def on_success(context: AuthContext) -> Response:
        received.append(context.user.subject)
        return JSONResponse({"authenticated": True})

    auth = GovBrAuth(on_success=on_success, clock=fixed_clock)
    app = FastAPI()
    app.include_router(auth.router)

    try:
        assert auth.runtime.fake is not None
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1:8000",
                follow_redirects=False,
            ) as http:
                login = await http.get("/auth/govbr/login")
                authorize = await http.get(_path(login.headers["location"]))
                request_match = re.search(
                    r'name="request" value="([^"]+)"',
                    authorize.text,
                )
                assert request_match is not None
                fake_login = await http.post(
                    "/fake-govbr/login",
                    data={
                        "request": request_match.group(1),
                        "cpf": "11122233344",
                        "password": "senha-ficticia",
                    },
                )
                callback = await http.get(_path(fake_login.headers["location"]))

        assert login.status_code == 302
        assert authorize.status_code == 200
        assert fake_login.status_code == 302
        assert callback.status_code == 200
        assert callback.json() == {"authenticated": True}
        assert received == ["11122233344"]
    finally:
        if not auth.runtime.is_closed:
            await auth.runtime.aclose()


@pytest.mark.asyncio
async def test_successful_callback_returns_the_same_validated_subject(
    browser: OAuthBrowser,
) -> None:
    result = await browser.authenticate()

    authorization_values = parse_qs(urlsplit(result.authorization_location).query)
    callback_values = parse_qs(urlsplit(result.callback_location).query)
    assert result.response.status_code == 200
    assert result.response.json() == {"sub": SUBJECT}
    assert browser.received_contexts[0].tokens is None
    assert len(authorization_values["state"][0]) >= 43
    assert len(callback_values["code"][0]) >= 43


@pytest.mark.asyncio
async def test_concurrent_logins_keep_transactions_isolated(
    browser: OAuthBrowser,
) -> None:
    first, second = await asyncio.gather(
        browser.authenticate(),
        browser.authenticate(),
    )

    first_state = parse_qs(urlsplit(first.authorization_location).query)["state"][0]
    second_state = parse_qs(urlsplit(second.authorization_location).query)["state"][0]
    assert first.response.status_code == 200
    assert first.response.json() == {"sub": SUBJECT}
    assert second.response.status_code == 200
    assert second.response.json() == {"sub": SUBJECT}
    assert first_state != second_state


@pytest.mark.asyncio
async def test_nonce_mismatch_returns_safe_authentication_failure(
    browser: OAuthBrowser,
    provider_variant: ProviderVariant,
) -> None:
    provider_variant.faults.nonce_override = "attacker-nonce"

    result = await browser.authenticate()

    assert result.response.status_code == 502
    assert result.response.json() == {
        "error": "invalid_id_token",
        "message": "Gov.br authentication failed.",
    }
    assert "attacker-nonce" not in result.response.text


@pytest.mark.asyncio
async def test_expired_state_returns_safe_bad_request(
    browser: OAuthBrowser,
) -> None:
    _, callback_location = await browser.authorize()
    token = _clock_value.set(FIXED_NOW + timedelta(minutes=6))

    try:
        response = await browser.callback(callback_location)
    finally:
        _clock_value.reset(token)

    assert response.status_code == 400
    assert response.json() == {
        "error": "expired_transaction",
        "message": "The authorization request is invalid or expired.",
    }
    assert parse_qs(urlsplit(callback_location).query)["state"][0] not in response.text


@pytest.mark.asyncio
async def test_authorization_code_replay_returns_safe_provider_rejection(
    browser: OAuthBrowser,
) -> None:
    result = await browser.authenticate()

    replay_response = await browser.callback(result.callback_location)

    assert result.response.status_code == 200
    assert replay_response.status_code == 502
    assert replay_response.json() == {
        "error": "provider_rejected",
        "message": "Gov.br rejected the request.",
    }
    replayed_state = parse_qs(urlsplit(result.callback_location).query)["state"][0]
    assert replayed_state not in replay_response.text


@pytest.mark.asyncio
async def test_provider_timeout_returns_safe_service_unavailable(
    browser: OAuthBrowser,
    provider_variant: ProviderVariant,
) -> None:
    provider_variant.faults.timeout_token_request = True

    result = await browser.authenticate()

    assert result.response.status_code == 503
    assert result.response.json() == {
        "error": "provider_unavailable",
        "message": "Gov.br is temporarily unavailable.",
    }
    assert "simulated provider timeout" not in result.response.text


@pytest.mark.asyncio
async def test_invalid_token_signature_returns_safe_authentication_failure(
    browser: OAuthBrowser,
    provider_variant: ProviderVariant,
) -> None:
    provider_variant.faults.invalid_signature = True

    result = await browser.authenticate()

    assert result.response.status_code == 502
    assert result.response.json() == {
        "error": "invalid_id_token",
        "message": "Gov.br authentication failed.",
    }


@pytest.mark.asyncio
async def test_subject_substitution_returns_safe_authentication_failure(
    browser: OAuthBrowser,
    provider_variant: ProviderVariant,
) -> None:
    provider_variant.faults.substituted_subject = "98765432100"

    result = await browser.authenticate()

    assert result.response.status_code == 502
    assert result.response.json() == {
        "error": "govbr_auth_error",
        "message": "Gov.br authentication failed.",
    }
    assert "98765432100" not in result.response.text
