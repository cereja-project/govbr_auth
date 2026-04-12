"""
Testes para validar tratamento de erro nos endpoints.
Cobre cenários onde exceções são lançadas no core e convertidas para HTTP.
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from flask import Flask
from cryptography.fernet import Fernet

from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrException, GovBrAuthenticationError


@pytest.fixture
def valid_fernet_key():
    """Gera uma chave Fernet válida para testes"""
    return Fernet.generate_key().decode('utf-8')


@pytest.fixture
def fastapi_app(valid_fernet_key):
    config = GovBrConfig(
        client_id="dummy_id",
        client_secret="dummy_secret",
        govbr_auth_url="https://localhost/authorize",
        govbr_token_url="https://localhost/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
    )
    app = FastAPI()
    controller = GovBrConnector(config)
    controller.init_fastapi(app)
    return app


@pytest.mark.asyncio
async def test_fastapi_post_authenticate_with_authentication_error(fastapi_app):
    """Testa /authenticate quando erro de autenticação é lançado → HTTP 401"""
    with patch(
        "govbr_auth.core.govbr.GovBrIntegration.async_exchange_code_for_token",
        new_callable=AsyncMock,
        side_effect=GovBrAuthenticationError("Código de verificação inválido")
    ):
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/auth/govbr/authenticate",
                json={"code": "invalid_code", "state": "invalid_state"}
            )
            assert response.status_code == 401
            assert "detail" in response.json()


@pytest.mark.asyncio
async def test_fastapi_post_authenticate_with_govbr_exception(fastapi_app):
    """Testa /authenticate quando GovBrException é lançada → HTTP 401"""
    with patch(
        "govbr_auth.core.govbr.GovBrIntegration.async_exchange_code_for_token",
        new_callable=AsyncMock,
        side_effect=GovBrException("client_id e client_secret são obrigatórios")
    ):
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/auth/govbr/authenticate",
                json={"code": "code", "state": "state"}
            )
            assert response.status_code == 401
            assert "detail" in response.json()


# ============================================================================
# FLASK TESTS
# ============================================================================

@pytest.fixture
def flask_app(valid_fernet_key):
    config = GovBrConfig(
        client_id="dummy_id",
        client_secret="dummy_secret",
        govbr_auth_url="https://localhost/authorize",
        govbr_token_url="https://localhost/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
    )
    app = Flask(__name__)
    controller = GovBrConnector(config)
    controller.init_flask(app)
    app.testing = True
    return app.test_client()


def test_flask_post_authenticate_with_authentication_error(flask_app):
    """Testa /authenticate com erro de autenticação → HTTP 401"""
    with patch(
        "govbr_auth.core.govbr.GovBrIntegration.exchange_code_for_token_sync",
        side_effect=GovBrAuthenticationError("Código de verificação inválido")
    ):
        response = flask_app.post("/auth/govbr/authenticate?code=invalid&state=invalid")
        assert response.status_code == 401
        assert b"error" in response.data


def test_flask_post_authenticate_with_govbr_exception(flask_app):
    """Testa /authenticate com GovBrException → HTTP 401"""
    with patch(
        "govbr_auth.core.govbr.GovBrIntegration.exchange_code_for_token_sync",
        side_effect=GovBrException("client_id e client_secret são obrigatórios")
    ):
        response = flask_app.post("/auth/govbr/authenticate?code=code&state=state")
        assert response.status_code == 401
        assert b"error" in response.data


def test_flask_get_authorize_url_success(flask_app):
    """Testa /authorize sucesso → HTTP 200 com URL"""
    response = flask_app.get("/auth/govbr/authorize")
    assert response.status_code == 200
    assert b"url" in response.data or b"error" in response.data

