"""Unit tests for the asynchronous FastAPI adapter."""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import Response
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
    create_govbr_runtime,
)

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class RecordingClient:
    """Represent the strict core at the adapter boundary."""

    def __init__(self, *, exchange_error: Exception | None = None) -> None:
        self.authorization_calls: list[datetime] = []
        self.exchange_calls: list[tuple[str, str, datetime]] = []
        self.userinfo_calls: list[tuple[SecretStr, str]] = []
        self.exchange_error = exchange_error
        self.tokens = TokenSet(
            access_token=SecretStr("unit-access-token"),
            id_token=SecretStr("unit-id-token"),
            token_type="Bearer",
            expires_in=300,
            scope="openid profile email",
        )

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        self.authorization_calls.append(now)
        return AuthorizationRequest(
            "https://sso.example.test/authorize?state=opaque", "opaque"
        )

    async def exchange_code(
        self,
        *,
        code: str,
        state: str,
        now: datetime,
    ) -> AuthenticationResult:
        self.exchange_calls.append((code, state, now))
        if self.exchange_error is not None:
            raise self.exchange_error
        return AuthenticationResult(
            tokens=self.tokens,
            id_token_claims={"sub": "12345678900", "email": "citizen@example.test"},
        )

    async def userinfo(
        self,
        access_token: SecretStr,
        *,
        expected_subject: str,
    ) -> GovBrUser:
        self.userinfo_calls.append((access_token, expected_subject))
        return GovBrUser(sub=expected_subject, name="Unit user")


def client_runtime(
    client: RecordingClient,
    *,
    owned_http: AsyncClient | None = None,
    redirect_uri: str | None = None,
) -> GovBrRuntime:
    """Build a real runtime around the adapter-boundary client."""
    oauth = None
    if redirect_uri is not None:
        oauth = GovBrSettings(
            authorization_url="https://sso.example.test/authorize",
            token_url="https://sso.example.test/token",
            userinfo_url="https://sso.example.test/userinfo",
            client_id="client-id",
            client_secret=SecretStr("client-secret"),
            redirect_uri=redirect_uri,
            transaction_secret=SecretStr("transaction-secret"),
            issuer="https://sso.example.test/",
            jwks_url="https://sso.example.test/jwks",
        )
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL, oauth=oauth),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=owned_http,
    )


async def request(app: FastAPI, path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get(path, follow_redirects=False)


def fake_runtime_settings() -> GovBrRuntimeSettings:
    return GovBrRuntimeSettings(provider=GovBrProvider.FAKE)


def colliding_fake_runtime() -> GovBrRuntime:
    return create_govbr_runtime(
        GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_provider_prefix="/auth/govbr",
        ),
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda __: httpx.Response(500)
        ),
        clock=lambda: FIXED_NOW,
    )


def test_fastapi_facade_exposes_read_only_router_without_install() -> None:
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    auth = GovBrAuth(
        runtime=client_runtime(RecordingClient()),
        on_success=success_handler,
    )

    assert isinstance(auth.router, APIRouter)
    assert not hasattr(auth, "install")
    with pytest.raises(AttributeError):
        auth.router = APIRouter()


@pytest.mark.asyncio
async def test_fastapi_facade_mounts_callback_at_configured_redirect_uri_path() -> None:
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    auth = GovBrAuth(
        runtime=client_runtime(
            RecordingClient(),
            redirect_uri=(
                "https://staging.example.test/oauth/govbr/caf%C3%A9%20retorno"
            ),
        ),
        on_success=success_handler,
    )
    app = FastAPI()
    app.include_router(auth.router)

    login = await request(app, "/auth/govbr/login")
    callback = await request(app, "/oauth/govbr/caf%C3%A9%20retorno")
    obsolete_callback = await request(app, "/auth/govbr/callback")

    assert login.status_code == 302
    assert callback.status_code == 422
    assert obsolete_callback.status_code == 404


def test_create_govbr_router_preserves_the_public_router_prefix() -> None:
    from govbr_auth.fastapi import create_govbr_router

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    router = create_govbr_router(
        client=RecordingClient(),
        on_success=success_handler,
        prefix="/custom-auth",
    )

    assert router.prefix == "/custom-auth"


@pytest.mark.asyncio
async def test_official_callback_path_is_validated_before_runtime_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import govbr_auth.adapters._runtime as adapter_runtime
    from govbr_auth.fastapi import GovBrAuth

    oauth = GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="client-id",
        client_secret=SecretStr("client-secret"),
        redirect_uri="https://staging.example.test/oauth%2Fgovbr/callback",
        transaction_secret=SecretStr("transaction-secret"),
        issuer="https://sso.example.test/",
        jwks_url="https://sso.example.test/jwks",
    )
    settings = GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL, oauth=oauth)
    allocated_http: list[AsyncClient] = []

    def allocate_runtime(*args, **kwargs) -> GovBrRuntime:
        del args, kwargs
        owned_http = AsyncClient()
        allocated_http.append(owned_http)
        return GovBrRuntime(
            settings=settings,
            client=RecordingClient(),
            provider=GovBrProvider.OFFICIAL,
            fake=None,
            _owned_http=owned_http,
        )

    monkeypatch.setattr(adapter_runtime, "create_govbr_runtime", allocate_runtime)

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    try:
        with pytest.raises(ValueError, match="redirect URI path is not route-safe"):
            GovBrAuth(
                settings=settings,
                on_success=success_handler,
            )
        assert allocated_http == []
    finally:
        for http in allocated_http:
            await http.aclose()


@pytest.mark.parametrize(
    "redirect_path",
    (
        "/oauth%2Fgovbr/callback",
        "/oauth%5Cgovbr/callback",
        "/oauth/{subject}/callback",
        "/oauth/<path:subject>/callback",
        "/oauth//callback",
    ),
)
def test_fastapi_facade_rejects_ambiguous_redirect_uri_paths(
    redirect_path: str,
) -> None:
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    with pytest.raises(ValueError, match="redirect URI path is not route-safe"):
        GovBrAuth(
            runtime=client_runtime(
                RecordingClient(),
                redirect_uri=f"https://staging.example.test{redirect_path}",
            ),
            on_success=success_handler,
        )


def test_fastapi_facade_rejects_callback_route_colliding_with_login() -> None:
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    with pytest.raises(
        ValueError,
        match="redirect URI callback path must differ from the login path",
    ):
        GovBrAuth(
            runtime=client_runtime(
                RecordingClient(),
                redirect_uri="https://staging.example.test/auth/govbr/login",
            ),
            on_success=success_handler,
        )


def test_fastapi_facade_rejects_settings_and_runtime_together() -> None:
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    settings = GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL)

    with pytest.raises(TypeError, match="settings and runtime are mutually exclusive"):
        GovBrAuth(
            settings=settings,
            runtime=client_runtime(RecordingClient()),
            on_success=success_handler,
        )


@pytest.mark.asyncio
async def test_fake_facade_uses_the_fake_adapter_transport_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consumer facade must use the neutral in-process fake transport."""
    import govbr_auth.fastapi as fastapi_adapter
    from govbr_auth.fastapi import GovBrAuth

    transported = []

    def create_transport(runtime, *, clock):
        transported.append((runtime, clock))
        return httpx.MockTransport(lambda request: httpx.Response(500))

    monkeypatch.setattr(fastapi_adapter, "FakeGovHttpTransport", create_transport)

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    auth = GovBrAuth(
        settings=fake_runtime_settings(),
        on_success=success_handler,
    )

    try:
        assert len(transported) == 1
        assert transported[0][0] is auth.runtime.fake
    finally:
        await auth.runtime.aclose()


@pytest.mark.asyncio
async def test_fake_facade_mounts_routes_with_simulator_http_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FastAPI registrar must pass the simulator facade into fake routes."""
    import govbr_auth.fake.fastapi as fake_fastapi
    from govbr_auth.fastapi import GovBrAuth

    mounted: list[tuple[object, object, object]] = []

    def create_router(runtime, *, application, clock):
        mounted.append((runtime, application, clock))
        return APIRouter()

    monkeypatch.setattr(fake_fastapi, "create_fake_govbr_router", create_router)

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    clock = lambda: FIXED_NOW
    auth = GovBrAuth(
        settings=fake_runtime_settings(),
        on_success=success_handler,
        clock=clock,
    )

    try:
        assert auth.runtime.fake is not None
        assert mounted == [
            (auth.runtime.fake, auth.runtime.fake.http_application, clock)
        ]
    finally:
        await auth.runtime.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "expected_message"),
    (
        ("auth", "prefix must be empty or start with '/'"),
        ("/auth/", "prefix must not end with '/'"),
        ("/auth?debug=1", "prefix must be an empty string or a canonical path"),
        ("/auth#fragment", "prefix must be an empty string or a canonical path"),
        ("//example.test/auth", "prefix must be an empty string or a canonical path"),
        ("/auth%2Fgovbr", "prefix must be an empty string or a canonical path"),
        ("/auth govbr", "prefix must be an empty string or a canonical path"),
        (r"/auth\govbr", "prefix must be an empty string or a canonical path"),
        ("/auth/./govbr", "prefix must be an empty string or a canonical path"),
        ("/auth/../govbr", "prefix must be an empty string or a canonical path"),
        ("/auth//govbr", "prefix must be an empty string or a canonical path"),
        ("/auth\x00govbr", "prefix must be an empty string or a canonical path"),
    ),
    ids=(
        "missing-leading-slash",
        "trailing-slash",
        "query",
        "fragment",
        "network-path",
        "percent-encoding",
        "whitespace",
        "backslash",
        "dot-segment",
        "parent-segment",
        "empty-segment",
        "control-character",
    ),
)
async def test_invalid_prefix_is_rejected_before_runtime_allocation(
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
    expected_message: str,
) -> None:
    import govbr_auth.fastapi as fastapi_adapter
    from govbr_auth.fastapi import GovBrAuth

    allocated_http: list[AsyncClient] = []

    def allocate_runtime(*args, **kwargs) -> GovBrRuntime:
        del args, kwargs
        owned_http = AsyncClient()
        allocated_http.append(owned_http)
        return client_runtime(RecordingClient(), owned_http=owned_http)

    monkeypatch.setattr(fastapi_adapter, "create_adapter_runtime", allocate_runtime)

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    raised: Exception | None = None
    try:
        GovBrAuth(
            settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL),
            on_success=success_handler,
            prefix=prefix,
        )
    except Exception as error:
        raised = error

    try:
        assert allocated_http == []
        assert isinstance(raised, ValueError)
        assert str(raised) == expected_message
    finally:
        for http in allocated_http:
            await http.aclose()


@pytest.mark.asyncio
async def test_fake_facade_aligns_default_redirect_with_custom_router_prefix() -> None:
    """A custom public router prefix must remain usable with the composed fake flow."""
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    auth = GovBrAuth(
        settings=fake_runtime_settings(),
        on_success=success_handler,
        prefix="/custom-auth",
    )

    try:
        assert auth.runtime.fake is not None
        assert str(
            auth.runtime.fake.settings.clients[0].registered_redirect_uris[0]
        ) == ("http://127.0.0.1:8000/custom-auth/callback")
    finally:
        await auth.runtime.aclose()


@pytest.mark.asyncio
async def test_fake_facade_rejects_supplied_runtime_with_mismatched_callback() -> None:
    """A caller-owned fake runtime must not mount under an inconsistent callback path."""
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    owner = GovBrAuth(
        settings=fake_runtime_settings(),
        on_success=success_handler,
    )

    raised: Exception | None = None
    try:
        try:
            GovBrAuth(
                runtime=owner.runtime,
                on_success=success_handler,
                prefix="/custom-auth",
            )
        except Exception as error:
            raised = error

        assert isinstance(raised, ValueError)
        assert str(raised) == (
            "fake runtime redirect URI does not match the adapter callback"
        )
    finally:
        await owner.runtime.aclose()


@pytest.mark.asyncio
async def test_router_lifespan_does_not_close_borrowed_runtime() -> None:
    from govbr_auth.fastapi import GovBrAuth

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    owned_http = AsyncClient()
    runtime = client_runtime(RecordingClient(), owned_http=owned_http)
    auth = GovBrAuth(runtime=runtime, on_success=success_handler)
    app = FastAPI()
    app.include_router(auth.router)

    async with app.router.lifespan_context(app):
        assert runtime.is_closed is False

    assert runtime.is_closed is False
    assert owned_http.is_closed is False
    await runtime.aclose()


@pytest.mark.asyncio
async def test_login_redirects_to_the_core_authorization_url() -> None:
    from govbr_auth.fastapi import create_govbr_router

    client = RecordingClient()

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client, on_success=success_handler, clock=lambda: FIXED_NOW
        )
    )

    response = await request(app, "/auth/govbr/login")

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == "https://sso.example.test/authorize?state=opaque"
    )
    assert client.authorization_calls == [FIXED_NOW]


@pytest.mark.asyncio
async def test_callback_binds_userinfo_to_validated_subject_and_exposes_tokens_only_when_opted_in() -> (
    None
):
    from govbr_auth.fastapi import create_govbr_router

    client = RecordingClient()
    received_contexts = []

    async def success_handler(context) -> Response:
        received_contexts.append(context)
        return Response(status_code=204)

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client,
            on_success=success_handler,
            expose_tokens=True,
            clock=lambda: FIXED_NOW,
        )
    )

    response = await request(app, "/auth/govbr/callback?code=code&state=state")

    assert response.status_code == 204
    assert client.exchange_calls == [("code", "state", FIXED_NOW)]
    assert client.userinfo_calls == [(client.tokens.access_token, "12345678900")]
    assert received_contexts[0].tokens is client.tokens


@pytest.mark.asyncio
async def test_callback_requires_code_and_state() -> None:
    from govbr_auth.fastapi import create_govbr_router

    client = RecordingClient()

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client, on_success=success_handler, clock=lambda: FIXED_NOW
        )
    )

    response = await request(app, "/auth/govbr/callback")

    assert response.status_code == 422
    assert client.exchange_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_name", "expected_code"),
    [
        pytest.param("InvalidStateError", "invalid_state", id="invalid_state"),
        pytest.param(
            "ExpiredTransactionError", "expired_transaction", id="replayed_state"
        ),
    ],
)
async def test_callback_maps_invalid_or_replayed_state_to_safe_bad_request(
    error_name: str,
    expected_code: str,
) -> None:
    from govbr_auth.fastapi import create_govbr_router
    from govbr_auth.core import errors

    client = RecordingClient(
        exchange_error=getattr(errors, error_name)("sensitive state")
    )

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client, on_success=success_handler, clock=lambda: FIXED_NOW
        )
    )

    response = await request(
        app, "/auth/govbr/callback?code=code&state=sensitive-state"
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": expected_code,
        "message": "The authorization request is invalid or expired.",
    }
    assert "sensitive" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_name", "status_code", "expected_code", "expected_message"),
    [
        pytest.param(
            "ProviderRejectedError",
            502,
            "provider_rejected",
            "Gov.br rejected the request.",
            id="provider_rejection",
        ),
        pytest.param(
            "ProviderUnavailableError",
            503,
            "provider_unavailable",
            "Gov.br is temporarily unavailable.",
            id="provider_unavailable",
        ),
    ],
)
async def test_callback_maps_upstream_failures_to_safe_responses(
    error_name: str,
    status_code: int,
    expected_code: str,
    expected_message: str,
) -> None:
    from govbr_auth.fastapi import create_govbr_router
    from govbr_auth.core import errors

    client = RecordingClient(
        exchange_error=getattr(errors, error_name)("sensitive provider detail")
    )

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client, on_success=success_handler, clock=lambda: FIXED_NOW
        )
    )

    response = await request(app, "/auth/govbr/callback?code=code&state=state")

    assert response.status_code == status_code
    assert response.json() == {"error": expected_code, "message": expected_message}
    assert "sensitive" not in response.text


@pytest.mark.asyncio
async def test_callback_delegates_authentication_failures_to_opted_in_handler() -> None:
    from govbr_auth.core.errors import InvalidStateError
    from govbr_auth.fastapi import create_govbr_router

    client = RecordingClient(exchange_error=InvalidStateError("sensitive state"))
    received_errors = []

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    async def error_handler(error) -> Response:
        received_errors.append(error)
        return Response(
            "<h1>Authentication failed</h1>",
            status_code=400,
            media_type="text/html",
        )

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client,
            on_success=success_handler,
            on_error=error_handler,
            clock=lambda: FIXED_NOW,
        )
    )

    response = await request(app, "/auth/govbr/callback?code=code&state=state")

    assert response.status_code == 400
    assert response.text == "<h1>Authentication failed</h1>"
    assert received_errors == [client.exchange_error]


@pytest.mark.asyncio
async def test_callback_propagates_handler_exceptions_unchanged() -> None:
    from govbr_auth.fastapi import create_govbr_router

    client = RecordingClient()
    expected_error = RuntimeError("handler failure")

    async def success_handler(context) -> Response:
        raise expected_error

    app = FastAPI()
    app.include_router(
        create_govbr_router(
            client=client, on_success=success_handler, clock=lambda: FIXED_NOW
        )
    )

    with pytest.raises(RuntimeError) as raised:
        await request(app, "/auth/govbr/callback?code=code&state=state")

    assert raised.value is expected_error


def test_fastapi_rejects_owned_fake_prefix_collision_before_runtime_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import govbr_auth.adapters._runtime as adapter_runtime
    from govbr_auth.fastapi import GovBrAuth

    allocations: list[object] = []

    def allocate_runtime(*args, **kwargs):
        allocations.append((args, kwargs))
        raise AssertionError("runtime must not be allocated")

    monkeypatch.setattr(adapter_runtime, "create_govbr_runtime", allocate_runtime)
    settings = GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_provider_prefix="/auth/govbr",
    )

    with pytest.raises(
        ValueError,
        match="o prefixo do FakeGov deve ser diferente do prefixo do adapter",
    ):
        GovBrAuth(
            settings=settings,
            on_success=lambda context: Response(status_code=204),
            clock=lambda: FIXED_NOW,
        )

    assert allocations == []


@pytest.mark.asyncio
async def test_fastapi_rejects_borrowed_fake_prefix_collision() -> None:
    from govbr_auth.fastapi import GovBrAuth

    runtime = colliding_fake_runtime()

    try:
        with pytest.raises(
            ValueError,
            match="o prefixo do FakeGov deve ser diferente do prefixo do adapter",
        ):
            GovBrAuth(
                runtime=runtime,
                on_success=lambda context: Response(status_code=204),
                clock=lambda: FIXED_NOW,
            )
    finally:
        await runtime.aclose()

