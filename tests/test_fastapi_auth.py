import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig
from govbr_auth.fastapi_ext.routes import get_router


@pytest.fixture
def app():
    config = GovBrConfig(
            client_id="dummy_id",
            client_secret="dummy_secret",
            auth_url="https://localhost/authorize",
            token_url="https://localhost/token",
            redirect_uri="https://localhost/callback",
            cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso=",
    )
    app = FastAPI()
    controller = GovBrConnector(config)
    controller.init_fastapi(app)
    return app


@pytest.mark.asyncio
async def test_get_url(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/auth/govbr/authorize")
        assert response.status_code == 200
        assert "url" in response.json() or "error" in response.json()
