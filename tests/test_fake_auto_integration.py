"""
Testes para validar a integração automática dos endpoints fake no controller.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
import base64

from govbr_auth import GovBrConfig, GovBrConnector, create_default_fake_users


@pytest.fixture
def valid_cript_secret():
    """Gera uma chave Fernet válida para testes"""
    return base64.urlsafe_b64encode(Fernet.generate_key()).decode('utf-8')[:44]


class TestFakeAutoIntegration:
    """Testes de integração automática do fake Gov.br"""

    def test_detect_fake_mode_by_localhost(self, valid_cript_secret):
        """Testa se detecta modo fake por URLs localhost"""
        config = GovBrConfig(
            client_id="test",
            client_secret="test",
            redirect_uri="http://localhost/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="http://localhost:8000/fake-govbr/authorize",
            govbr_token_url="http://localhost:8000/fake-govbr/token"
        )

        connector = GovBrConnector(config=config)

        assert connector.is_fake_mode is True
        assert connector.fake_service is not None

    def test_detect_real_mode(self, valid_cript_secret):
        """Testa se detecta modo real por URLs do Gov.br"""
        config = GovBrConfig(
            client_id="test",
            client_secret="test",
            redirect_uri="https://example.com/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="https://sso.staging.acesso.gov.br/authorize",
            govbr_token_url="https://sso.staging.acesso.gov.br/token"
        )

        connector = GovBrConnector(config=config)

        assert connector.is_fake_mode is False
        assert connector.fake_service is None

    def test_fake_endpoints_registered_fastapi(self, valid_cript_secret):
        """Testa se os endpoints fake são registrados automaticamente no FastAPI"""
        app = FastAPI()

        config = GovBrConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8000/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="http://localhost:8000/fake-govbr/authorize",
            govbr_token_url="http://localhost:8000/fake-govbr/token"
        )

        connector = GovBrConnector(
            config=config,
            fake_users=create_default_fake_users()
        )
        connector.init_fastapi(app)

        client = TestClient(app)

        # Testa se endpoint /authorize existe
        response = client.get("/auth/govbr/authorize")
        assert response.status_code == 200

        # Testa se endpoint fake /fake-govbr/users existe
        response = client.get("/fake-govbr/users")
        assert response.status_code == 200
        assert "usuarios_de_teste" in response.json()

        # Verifica se tem 3 usuários padrão
        users = response.json()["usuarios_de_teste"]
        assert len(users) == 3

    def test_fake_authorize_endpoint(self, valid_cript_secret):
        """Testa se o endpoint fake /authorize retorna página HTML"""
        app = FastAPI()

        config = GovBrConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8000/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="http://localhost:8000/fake-govbr/authorize",
            govbr_token_url="http://localhost:8000/fake-govbr/token"
        )

        connector = GovBrConnector(config=config)
        connector.init_fastapi(app)

        client = TestClient(app)

        # Testa o endpoint fake authorize
        response = client.get(
            "/fake-govbr/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client",
                "scope": "openid profile email",
                "redirect_uri": "http://localhost:8000/callback",
                "state": "test-state",
                "nonce": "test-nonce",
                "code_challenge": "test-challenge",
                "code_challenge_method": "S256"
            }
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Gov.br" in response.text  # Página de login
        assert "CPF" in response.text
        assert "E-mail" in response.text

    def test_custom_fake_users(self, valid_cript_secret):
        """Testa se aceita usuários fake personalizados"""
        from govbr_auth import FakeUserData

        app = FastAPI()

        custom_users = {
            "99999999999": FakeUserData(
                cpf="99999999999",
                nome="Usuário Teste",
                email="teste@example.com"
            )
        }

        config = GovBrConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8000/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="http://localhost:8000/fake-govbr/authorize",
            govbr_token_url="http://localhost:8000/fake-govbr/token"
        )

        connector = GovBrConnector(
            config=config,
            fake_users=custom_users
        )
        connector.init_fastapi(app)

        client = TestClient(app)

        # Verifica se os usuários personalizados foram carregados
        response = client.get("/fake-govbr/users")
        users = response.json()["usuarios_de_teste"]

        assert len(users) == 1
        assert users[0]["cpf"] == "99999999999"
        assert users[0]["nome"] == "Usuário Teste"

    def test_real_mode_no_fake_endpoints(self, valid_cript_secret):
        """Testa que endpoints fake NÃO são criados em modo real"""
        app = FastAPI()

        config = GovBrConfig(
            client_id="test",
            client_secret="test",
            redirect_uri="https://example.com/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="https://sso.staging.acesso.gov.br/authorize",
            govbr_token_url="https://sso.staging.acesso.gov.br/token"
        )

        connector = GovBrConnector(config=config)
        connector.init_fastapi(app)

        client = TestClient(app)

        # Testa se endpoint /authorize normal existe
        response = client.get("/auth/govbr/authorize")
        assert response.status_code == 200

        # Testa se endpoints fake NÃO existem
        response = client.get("/fake-govbr/users")
        assert response.status_code == 404  # Não deve existir em modo real

    def test_detect_fake_mode_by_127_0_0_1(self, valid_cript_secret):
        """Testa detecção de modo fake com IP 127.0.0.1"""
        config = GovBrConfig(
            client_id="test",
            client_secret="test",
            redirect_uri="http://127.0.0.1/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="http://127.0.0.1:8000/fake-govbr/authorize",
            govbr_token_url="http://127.0.0.1:8000/fake-govbr/token"
        )

        connector = GovBrConnector(config=config)

        assert connector.is_fake_mode is True
        assert connector.fake_service is not None

    def test_force_fake_mode_with_flag(self, valid_cript_secret):
        """Força modo fake via flag mesmo com URLs não locais."""
        config = GovBrConfig(
            client_id="test",
            client_secret="test",
            redirect_uri="https://example.com/callback",
            cript_verifier_secret=valid_cript_secret,
            govbr_auth_url="https://sso.acesso.gov.br/authorize",
            govbr_token_url="https://sso.acesso.gov.br/token",
            use_fake=True,
        )

        connector = GovBrConnector(config=config)

        assert connector.is_fake_mode is True
        assert connector.fake_service is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
