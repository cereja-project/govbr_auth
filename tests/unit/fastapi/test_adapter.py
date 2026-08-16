"""Unit tests for the asynchronous FastAPI adapter."""

from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse, Response
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.runtime import GovBrProvider, GovBrRuntime, GovBrRuntimeSettings

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
) -> GovBrRuntime:
    """Build a real runtime around the adapter-boundary client."""
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=owned_http,
    )


async def request(app: FastAPI, path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get(path, follow_redirects=False)


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
async def test_router_lifespan_closes_runtime() -> None:
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

    assert runtime.is_closed is True
    assert owned_http.is_closed is True


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
