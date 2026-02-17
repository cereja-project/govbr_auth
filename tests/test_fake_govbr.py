"""
Testes unitários para o FakeGovBrService.

Testa todas as funcionalidades do simulador Gov.br incluindo:
- Criação de sessões
- Autenticação de usuários
- Troca de códigos por tokens
- Validação PKCE
- Expiração de sessões e códigos
"""

import pytest
import time
import jwt as pyjwt

from govbr_auth import (
    FakeGovBrService,
    FakeUserData,
    create_default_fake_users,
    render_fake_login_page,
    process_fake_login,
    AuthorizationRequest
)


class TestFakeUserData:
    """Testes para o modelo FakeUserData"""

    def test_create_user_minimal(self):
        """Testa criação de usuário com dados mínimos"""
        user = FakeUserData(
            cpf="12345678901",
            nome="Teste User",
            email="teste@example.com"
        )

        assert user.cpf == "12345678901"
        assert user.nome == "Teste User"
        assert user.email == "teste@example.com"
        assert "gov.br" in user.picture  # Foto padrão

    def test_create_user_with_picture(self):
        """Testa criação de usuário com foto personalizada"""
        user = FakeUserData(
            cpf="12345678901",
            nome="Teste User",
            email="teste@example.com",
            picture="https://example.com/foto.jpg"
        )

        assert user.picture == "https://example.com/foto.jpg"


class TestFakeGovBrService:
    """Testes para o FakeGovBrService"""

    @pytest.fixture
    def users(self):
        """Fixture com usuários de teste"""
        return {
            "12345678901": FakeUserData(
                cpf="12345678901",
                nome="João Teste",
                email="joao@test.com"
            ),
            "98765432100": FakeUserData(
                cpf="98765432100",
                nome="Maria Teste",
                email="maria@test.com"
            )
        }

    @pytest.fixture
    def service(self, users):
        """Fixture com serviço configurado"""
        return FakeGovBrService(
            users=users,
            session_ttl=600,
            jwt_secret="test-secret-key",
            client_id="test-client-id"
        )

    def test_service_initialization(self, users):
        """Testa inicialização do serviço"""
        service = FakeGovBrService(
            users=users,
            session_ttl=300,
            jwt_secret="secret",
            client_id="client"
        )

        assert service.users == users
        assert service.session_ttl == 300
        assert service.jwt_secret == "secret"
        assert service.client_id == "client"
        assert len(service._sessions) == 0
        assert len(service._authorization_codes) == 0

    def test_create_session(self, service):
        """Testa criação de sessão"""
        request_id = service.create_session(
            state="test-state",
            code_challenge="test-challenge",
            redirect_uri="http://localhost/callback",
            nonce="test-nonce",
            scope="openid profile email"
        )

        assert request_id is not None
        assert len(request_id) > 0

        # Verifica se a sessão foi armazenada
        session = service._sessions[request_id]
        assert session["state"] == "test-state"
        assert session["code_challenge"] == "test-challenge"
        assert session["redirect_uri"] == "http://localhost/callback"
        assert session["nonce"] == "test-nonce"
        assert session["scope"] == "openid profile email"
        assert "created_at" in session
        assert "expires_at" in session

    def test_get_session_valid(self, service):
        """Testa recuperação de sessão válida"""
        request_id = service.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        session = service.get_session(request_id)

        assert session["state"] == "state"
        assert session["code_challenge"] == "challenge"

    def test_get_session_not_found(self, service):
        """Testa erro ao buscar sessão inexistente"""
        with pytest.raises(ValueError, match="Sessão não encontrada"):
            service.get_session("invalid-request-id")

    def test_get_session_expired(self, service):
        """Testa erro ao buscar sessão expirada"""
        # Cria serviço com TTL muito curto
        service_short_ttl = FakeGovBrService(
            users=service.users,
            session_ttl=1,  # 1 segundo
            jwt_secret="secret",
            client_id="client"
        )

        request_id = service_short_ttl.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        # Aguarda expiração
        time.sleep(2)

        with pytest.raises(ValueError, match="Sessão expirada"):
            service_short_ttl.get_session(request_id)

    def test_authenticate_user_success(self, service):
        """Testa autenticação de usuário com sucesso"""
        request_id = service.create_session(
            state="state123",
            code_challenge="challenge456",
            redirect_uri="http://localhost/callback",
            nonce="nonce789"
        )

        redirect_url = service.authenticate_user(
            request_id=request_id,
            email="joao@test.com",
            cpf="12345678901"
        )

        assert "http://localhost/callback" in redirect_url
        assert "code=" in redirect_url
        assert "state=state123" in redirect_url

        # Verifica se a sessão foi removida
        assert request_id not in service._sessions

    def test_authenticate_user_cpf_not_found(self, service):
        """Testa erro quando CPF não existe"""
        request_id = service.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        with pytest.raises(ValueError, match="CPF não encontrado"):
            service.authenticate_user(
                request_id=request_id,
                email="test@test.com",
                cpf="99999999999"
            )

    def test_authenticate_user_email_mismatch(self, service):
        """Testa erro quando e-mail não corresponde ao CPF"""
        request_id = service.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        with pytest.raises(ValueError, match="E-mail não corresponde"):
            service.authenticate_user(
                request_id=request_id,
                email="wrong@test.com",
                cpf="12345678901"
            )

    def test_authenticate_user_cpf_formatting(self, service):
        """Testa autenticação com CPF formatado"""
        request_id = service.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        # CPF com formatação deve funcionar
        redirect_url = service.authenticate_user(
            request_id=request_id,
            email="joao@test.com",
            cpf="123.456.789-01"
        )

        assert "code=" in redirect_url

    def test_exchange_code_for_token_success(self, service):
        """Testa troca de código por token com sucesso"""
        # Simula autenticação completa
        request_id = service.create_session(
            state="state",
            code_challenge="n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg",  # SHA256 de "test"
            redirect_uri="http://test.com/callback",
            nonce="nonce123"
        )

        redirect_url = service.authenticate_user(
            request_id=request_id,
            email="joao@test.com",
            cpf="12345678901"
        )

        # Extrai o código da URL
        code = redirect_url.split("code=")[1].split("&")[0]

        # Troca por token
        token_response = service.exchange_code_for_token(
            code=code,
            code_verifier="test",  # Original que gerou o challenge
            redirect_uri="http://test.com/callback",
            client_id="test-client"
        )

        assert "access_token" in token_response
        assert "id_token" in token_response
        assert "token_type" in token_response
        assert token_response["token_type"] == "Bearer"
        assert token_response["expires_in"] == 3600
        assert "scope" in token_response

        # Valida o id_token
        decoded = pyjwt.decode(
            token_response["id_token"],
            service.jwt_secret,
            algorithms=["HS256"],
            audience="test-client",
            options={"verify_signature": True}
        )

        assert decoded["sub"] == "12345678901"
        assert decoded["name"] == "João Teste"
        assert decoded["email"] == "joao@test.com"
        assert decoded["cpf"] == "12345678901"
        assert decoded["nonce"] == "nonce123"
        assert decoded["aud"] == "test-client"

        # Verifica se o código foi removido
        with pytest.raises(ValueError):
            service.exchange_code_for_token(
                code=code,
                code_verifier="test",
                redirect_uri="http://test.com/callback"
            )

    def test_exchange_code_invalid_code(self, service):
        """Testa erro com código inválido"""
        with pytest.raises(ValueError, match="inválido ou expirado"):
            service.exchange_code_for_token(
                code="invalid-code",
                code_verifier="test",
                redirect_uri="http://test.com"
            )

    def test_exchange_code_wrong_verifier(self, service):
        """Testa erro com code_verifier incorreto"""
        request_id = service.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        redirect_url = service.authenticate_user(
            request_id=request_id,
            email="joao@test.com",
            cpf="12345678901"
        )

        code = redirect_url.split("code=")[1].split("&")[0]

        with pytest.raises(ValueError, match="code_verifier inválido"):
            service.exchange_code_for_token(
                code=code,
                code_verifier="wrong-verifier",
                redirect_uri="http://test.com"
            )

    def test_exchange_code_wrong_redirect_uri(self, service):
        """Testa erro com redirect_uri diferente"""
        request_id = service.create_session(
            state="state",
            code_challenge="n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        redirect_url = service.authenticate_user(
            request_id=request_id,
            email="joao@test.com",
            cpf="12345678901"
        )

        code = redirect_url.split("code=")[1].split("&")[0]

        with pytest.raises(ValueError, match="redirect_uri não corresponde"):
            service.exchange_code_for_token(
                code=code,
                code_verifier="test",
                redirect_uri="http://different.com"
            )

    def test_cleanup_expired(self, service):
        """Testa limpeza de sessões e códigos expirados"""
        # Cria serviço com TTL curto
        service_short = FakeGovBrService(
            users=service.users,
            session_ttl=1,
            jwt_secret="secret",
            client_id="client"
        )

        # Cria sessão que vai expirar
        request_id = service_short.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        assert len(service_short._sessions) == 1

        # Aguarda expiração
        time.sleep(2)

        # Executa limpeza
        service_short.cleanup_expired()

        assert len(service_short._sessions) == 0


class TestHelperFunctions:
    """Testes para funções auxiliares"""

    def test_create_default_fake_users(self):
        """Testa criação de usuários padrão"""
        users = create_default_fake_users()

        assert len(users) == 3
        assert "12345678901" in users
        assert "98765432100" in users
        assert "11122233344" in users

        assert users["12345678901"].nome == "João da Silva"
        assert users["98765432100"].email == "maria.oliveira@example.com"

    def test_render_fake_login_page(self):
        """Testa renderização da página de login"""
        service = FakeGovBrService(
            users=create_default_fake_users(),
            jwt_secret="secret",
            client_id="client"
        )

        auth_request = AuthorizationRequest(
            response_type="code",
            client_id="test-client",
            scope="openid profile email",
            redirect_uri="http://test.com/callback",
            state="test-state",
            nonce="test-nonce",
            code_challenge="test-challenge",
            code_challenge_method="S256"
        )

        html, request_id = render_fake_login_page(service, auth_request)

        assert request_id is not None
        assert request_id in html
        assert "Gov.br" in html
        assert "CPF" in html
        assert "E-mail" in html

    def test_process_fake_login(self):
        """Testa processamento do login"""
        service = FakeGovBrService(
            users=create_default_fake_users(),
            jwt_secret="secret",
            client_id="client"
        )

        request_id = service.create_session(
            state="state",
            code_challenge="challenge",
            redirect_uri="http://test.com",
            nonce="nonce"
        )

        redirect_url = process_fake_login(
            service=service,
            request_id=request_id,
            email="joao.silva@example.com",
            cpf="12345678901"
        )

        assert "http://test.com" in redirect_url
        assert "code=" in redirect_url
        assert "state=" in redirect_url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

