"""Freeze the FastAPI adapter public contract."""

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
)

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class ContractClient:
    """Provide deterministic core results at the FastAPI boundary."""

    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = claims
        self.tokens = TokenSet(
            access_token=SecretStr("contract-access-token"),
            id_token=SecretStr("contract-id-token"),
            token_type="Bearer",
            expires_in=300,
            scope="openid profile email",
        )

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        return AuthorizationRequest("https://sso.example.test/authorize", "state")

    async def exchange_code(
        self,
        *,
        code: str,
        state: str,
        now: datetime,
    ) -> AuthenticationResult:
        return AuthenticationResult(tokens=self.tokens, id_token_claims=self.claims)

    async def userinfo(
        self,
        access_token: SecretStr,
        *,
        expected_subject: str,
    ) -> GovBrUser:
        return GovBrUser(sub=expected_subject, name="Contract user")


def contract_runtime(client: ContractClient) -> GovBrRuntime:
    """Wrap the deterministic client in the facade's neutral runtime contract."""
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=None,
    )


def route_paths(app: FastAPI) -> set[str]:
    paths: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        path = getattr(route, "path", "")
        if path.startswith(("/auth", "/fake-govbr")):
            paths.add(path)
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            pending.extend(included_router.routes)
    return paths


def test_application_settings_reject_missing_official_oauth_before_route_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import govbr_auth.fastapi as fastapi_adapter
    import govbr_auth.runtime as runtime_module
    from govbr_auth.fastapi import GovBrAuth

    allocated_routers: list[object] = []
    allocated_http_clients: list[object] = []
    original_router = fastapi_adapter.APIRouter

    def record_router(*args, **kwargs):
        router = original_router(*args, **kwargs)
        allocated_routers.append(router)
        return router

    def record_http_client(*args, **kwargs):
        del args, kwargs
        allocated_http_clients.append(object())
        raise AssertionError("HTTP client must not be allocated")

    monkeypatch.setattr(fastapi_adapter, "APIRouter", record_router)
    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", record_http_client)
    settings = GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL)

    with pytest.raises(ValueError, match="official runtime requires OAuth settings"):
        GovBrAuth(
            settings=settings,
            on_success=lambda context: Response(status_code=204),
            clock=lambda: FIXED_NOW,
        )

    assert allocated_routers == []
    assert allocated_http_clients == []


@pytest.mark.asyncio
async def test_callback_context_is_frozen_copies_claims_and_omits_tokens_by_default() -> (
    None
):
    from govbr_auth.fastapi import GovBrAuth

    original_claims: dict[str, object] = {"sub": "12345678900", "role": "citizen"}
    client = ContractClient(original_claims)
    received_contexts = []

    async def success_handler(context):
        received_contexts.append(context)
        return RedirectResponse("/signed-in", status_code=303)

    app = FastAPI()
    auth = GovBrAuth(
        runtime=contract_runtime(client),
        on_success=success_handler,
        clock=lambda: FIXED_NOW,
    )
    app.include_router(auth.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/auth/govbr/callback?code=code&state=state")

    original_claims["role"] = "changed-after-callback"
    context = received_contexts[0]

    assert response.status_code == 303
    assert response.headers["location"] == "/signed-in"
    assert context.user.subject == "12345678900"
    assert context.claims == {"sub": "12345678900", "role": "citizen"}
    assert isinstance(context.claims, MappingProxyType)
    assert context.tokens is None
    with pytest.raises(TypeError):
        context.claims["role"] = "attacker"
    with pytest.raises(AttributeError):
        context.user = GovBrUser(sub="different-subject")


def test_router_facade_exposes_consumer_routes_without_installation_method() -> None:
    from govbr_auth.fastapi import GovBrAuth

    client = ContractClient({"sub": "12345678900"})

    async def success_handler(context) -> Response:
        return Response(status_code=204)

    app = FastAPI()
    auth = GovBrAuth(
        runtime=contract_runtime(client),
        on_success=success_handler,
        clock=lambda: FIXED_NOW,
    )
    app.include_router(auth.router)

    expected_paths = {"/auth/govbr/login", "/auth/govbr/callback"}
    assert route_paths(app) == expected_paths
    assert not hasattr(auth, "install")
    assert not any(path.startswith("/fake-govbr") for path in route_paths(app))
