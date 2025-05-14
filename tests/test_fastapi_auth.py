from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig


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

@pytest.fixture
def mock_async_exchange_code_for_token():
    with patch(
            "govbr_auth.core.govbr.GovBrIntegration.async_exchange_code_for_token",
            new_callable=AsyncMock,
    ) as mock_function:
        yield mock_function


@pytest.mark.asyncio
async def test_get_url(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/auth/govbr/authorize")
        assert response.status_code == 200
        assert "url" in response.json() or "error" in response.json()


@pytest.mark.asyncio
async def test_post_url(app, mock_async_exchange_code_for_token):
    # Mock da resposta do Gov.br
    mock_case = {
        "sub":   "12345678900",
        "email": "test@example.com",
        "name":  "Nome da pessoa cadastrada no banco",
    }
    mock_async_exchange_code_for_token.return_value = {"id_token": "fake", "id_token_decoded": mock_case}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/auth/govbr/authenticate", json={"code":  "mock-code-1234",
                                                                   "state": "gAAAAABoJAG9YX0ASaIlxtAIH22F4_z1hDg7n8yt7d9b6qXMcP1TlAMGybES_2C1_QfCh7t6yU4eUM5XjVlZP9b4rVoWh67TgB-po1uRw_NefZzlnXSWBA9MeZzuwDxanGAe0v5u9G5FhGMTeTNxWExj_EwQVH3znkBqnmnnQIrilp9ykzrg1QEPHuspxJ6HrY01LM1nPc9_FPkTPShfw2YH2BMb3I436Q=="})
        assert response.status_code == 200
        assert "id_token" in response.json()
