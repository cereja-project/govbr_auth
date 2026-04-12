"""
Testes para verificação de JWT com JWKS e fallback HS256.
Cobre validação de assinatura RSA, HS256 e cenários de erro.
"""

import pytest
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from govbr_auth.core.govbr import GovBrIntegration, GovBrAuthenticationError
from govbr_auth.core.config import GovBrConfig
from cryptography.fernet import Fernet


# ============================================================================
# Fixtures para geração de tokens de teste
# ============================================================================

@pytest.fixture
def rsa_key_pair():
    """Gera um par RSA para testes"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem,
    }


@pytest.fixture
def valid_fernet_key():
    """Gera uma chave Fernet válida para testes"""
    return Fernet.generate_key().decode('utf-8')


@pytest.fixture
def govbr_config_prod(valid_fernet_key):
    """Config com URLs de produção (Gov.br real)"""
    return GovBrConfig(
        client_id="test_client_id",
        client_secret="test_secret",
        govbr_auth_url="https://sso.acesso.gov.br/authorize",
        govbr_token_url="https://sso.acesso.gov.br/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
    )


@pytest.fixture
def govbr_config_staging(valid_fernet_key):
    """Config com URLs de staging"""
    return GovBrConfig(
        client_id="test_client_id",
        client_secret="test_secret",
        govbr_auth_url="https://sso.staging.acesso.gov.br/authorize",
        govbr_token_url="https://sso.staging.acesso.gov.br/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
    )


@pytest.fixture
def govbr_config_local_with_secret(valid_fernet_key):
    """Config local com jwt_secret configurado (fake mode)"""
    return GovBrConfig(
        client_id="test_client_id",
        client_secret="test_secret",
        govbr_auth_url="https://localhost/authorize",
        govbr_token_url="https://localhost/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
        jwt_secret="fake-dev-secret-key-123456",
        jwt_algorithm="HS256",
    )


def create_rsa_token(private_key, client_id, expired=False, wrong_audience=False):
    """Cria um token RSA assinado para testes"""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "https://sso.acesso.gov.br",
        "sub": "12345678901",
        "aud": wrong_audience and "different_client_id" or client_id,
        "exp": (now + timedelta(hours=-1 if expired else 1)).timestamp(),
        "iat": now.timestamp(),
        "name": "Test User",
        "email": "test@example.com",
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256")


def create_hs256_token(secret, client_id, expired=False, wrong_audience=False):
    """Cria um token HS256 assinado para testes"""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "https://localhost",
        "sub": "12345678901",
        "aud": wrong_audience and "different_client_id" or client_id,
        "exp": (now + timedelta(hours=-1 if expired else 1)).timestamp(),
        "iat": now.timestamp(),
        "name": "Test User",
        "email": "test@example.com",
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def create_unverified_token(client_id):
    """Cria um token sem validação (para teste de verify=False)"""
    return create_hs256_token("any-secret", client_id)


# ============================================================================
# Testes: JWKS com RSA (Production/Staging)
# ============================================================================

@pytest.mark.asyncio
async def test_jwt_decode_with_jwks_valid_token(govbr_config_prod, rsa_key_pair):
    """
    Testa decodificação de token RSA válido com JWKS.
    Simula verificação com chave pública do Gov.br.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_prod)
    token = create_rsa_token(rsa_key_pair["private_key"], govbr_config_prod.client_id)

    # Mock PyJWKClient e seu método
    mock_signing_key = Mock()
    mock_signing_key.key = rsa_key_pair["public_key"]

    mock_jwks_client = Mock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    # Mock pyjwt.decode para evitar clock skew issues em testes
    with patch.object(integration, "_get_jwks_client", return_value=mock_jwks_client):
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "12345678901",
                "email": "test@example.com",
                "aud": govbr_config_prod.client_id,
            }
            # Act
            payload = integration.jwt_payload_decode(token, verify=True)

    # Assert
    assert payload["sub"] == "12345678901"
    assert payload["email"] == "test@example.com"
    assert payload["aud"] == govbr_config_prod.client_id


@pytest.mark.asyncio
async def test_jwt_decode_with_jwks_invalid_signature(govbr_config_prod, rsa_key_pair):
    """
    Testa que token com assinatura RSA inválida é rejeitado.
    PyJWKClient.get_signing_key_from_jwt() lança PyJWTError.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_prod)
    token = create_rsa_token(rsa_key_pair["private_key"], govbr_config_prod.client_id)

    # Mock PyJWKClient para lançar erro (assinatura inválida)
    mock_jwks_client = Mock()
    mock_jwks_client.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.InvalidSignatureError("Invalid signature")

    with patch.object(integration, "_get_jwks_client", return_value=mock_jwks_client):
        # Act & Assert
        with pytest.raises(GovBrAuthenticationError) as exc_info:
            integration.jwt_payload_decode(token, verify=True)

        assert "JWT signature verification failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_jwt_decode_with_jwks_token_expired(govbr_config_prod, rsa_key_pair):
    """
    Testa que token RSA expirado é rejeitado.
    verify_exp=True deve validar o claim 'exp'.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_prod)
    token = create_rsa_token(rsa_key_pair["private_key"], govbr_config_prod.client_id, expired=True)

    # Mock PyJWKClient
    mock_signing_key = Mock()
    mock_signing_key.key = rsa_key_pair["public_key"]

    mock_jwks_client = Mock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with patch.object(integration, "_get_jwks_client", return_value=mock_jwks_client):
        # Mock pyjwt.decode para simular token expirado
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.exceptions.ExpiredSignatureError("Token expired")
            # Act & Assert
            with pytest.raises(GovBrAuthenticationError) as exc_info:
                integration.jwt_payload_decode(token, verify=True)

            assert "JWT signature verification failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_jwt_decode_with_jwks_audience_mismatch(govbr_config_prod, rsa_key_pair):
    """
    Testa que token com audience diferente é rejeitado.
    verify_aud=True deve validar que 'aud' == client_id.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_prod)
    token = create_rsa_token(rsa_key_pair["private_key"], govbr_config_prod.client_id, wrong_audience=True)

    # Mock PyJWKClient
    mock_signing_key = Mock()
    mock_signing_key.key = rsa_key_pair["public_key"]

    mock_jwks_client = Mock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with patch.object(integration, "_get_jwks_client", return_value=mock_jwks_client):
        # Mock pyjwt.decode para simular audience mismatch
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.exceptions.InvalidAudienceError("Invalid audience")
            # Act & Assert
            with pytest.raises(GovBrAuthenticationError) as exc_info:
                integration.jwt_payload_decode(token, verify=True)

            assert "JWT signature verification failed" in str(exc_info.value)


# ============================================================================
# Testes: Fallback HS256 (Local/Fake Mode)
# ============================================================================

@pytest.mark.asyncio
async def test_jwt_decode_with_hs256_fallback_valid_token(govbr_config_local_with_secret):
    """
    Testa decodificação HS256 quando JWKS não está disponível.
    Simula modo local/fake com jwt_secret configurado.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_local_with_secret)
    token = create_hs256_token(
        govbr_config_local_with_secret.jwt_secret,
        govbr_config_local_with_secret.client_id
    )

    # Mock JWKS como None (não disponível em localhost)
    with patch.object(integration, "_get_jwks_client", return_value=None):
        # Mock pyjwt.decode para evitar clock skew
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "12345678901",
                "email": "test@example.com",
                "aud": govbr_config_local_with_secret.client_id,
            }
            # Act
            payload = integration.jwt_payload_decode(token, verify=True)

    # Assert
    assert payload["sub"] == "12345678901"
    assert payload["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_jwt_decode_with_hs256_fallback_invalid_signature(govbr_config_local_with_secret):
    """
    Testa que token HS256 com assinatura inválida é rejeitado.
    Token foi assinado com secret diferente.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_local_with_secret)
    # Token assinado com secret diferente
    token = create_hs256_token("wrong-secret", govbr_config_local_with_secret.client_id)

    # Mock JWKS como None
    with patch.object(integration, "_get_jwks_client", return_value=None):
        # Mock pyjwt.decode para simular assinatura inválida
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.exceptions.InvalidSignatureError("Invalid signature")
            # Act & Assert
            with pytest.raises(GovBrAuthenticationError) as exc_info:
                integration.jwt_payload_decode(token, verify=True)

            assert "JWT verification failed with configured secret" in str(exc_info.value)


@pytest.mark.asyncio
async def test_jwt_decode_with_hs256_fallback_token_expired(govbr_config_local_with_secret):
    """
    Testa que token HS256 expirado é rejeitado.
    verify_exp=True deve validar o claim 'exp'.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_local_with_secret)
    token = create_hs256_token(
        govbr_config_local_with_secret.jwt_secret,
        govbr_config_local_with_secret.client_id,
        expired=True
    )
    
    # Mock JWKS como None
    with patch.object(integration, "_get_jwks_client", return_value=None):
        # Mock pyjwt.decode para simular token expirado
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.exceptions.ExpiredSignatureError("Token expired")
            # Act & Assert
            with pytest.raises(GovBrAuthenticationError) as exc_info:
                integration.jwt_payload_decode(token, verify=True)
            
            assert "JWT verification failed with configured secret" in str(exc_info.value)


# ============================================================================
# Testes: Unverified Decode (Fake Mode sem verificação)
# ============================================================================

@pytest.mark.asyncio
async def test_jwt_decode_unverified_mode(govbr_config_local_with_secret):
    """
    Testa decodificação sem verificação quando verify=False.
    Deve aceitar qualquer token válido JWT, mesmo com assinatura errada.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_local_with_secret)
    # Token assinado com secret diferente (seria inválido se verify=True)
    token = create_hs256_token("wrong-secret", govbr_config_local_with_secret.client_id)
    
    # Mock pyjwt.decode para evitar clock skew
    with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
        mock_decode.return_value = {
            "sub": "12345678901",
            "email": "test@example.com",
        }
        # Act
        payload = integration.jwt_payload_decode(token, verify=False)
    
    # Assert
    assert payload["sub"] == "12345678901"
    assert payload["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_jwt_decode_unverified_mode_ignores_expiration(govbr_config_local_with_secret):
    """
    Testa que verify=False aceita token expirado.
    """
    # Arrange
    integration = GovBrIntegration(govbr_config_local_with_secret)
    token = create_hs256_token(
        govbr_config_local_with_secret.jwt_secret,
        govbr_config_local_with_secret.client_id,
        expired=True
    )

    # Mock pyjwt.decode para evitar clock skew
    with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
        mock_decode.return_value = {
            "sub": "12345678901",
            "email": "test@example.com",
            "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(),
        }
        # Act
        payload = integration.jwt_payload_decode(token, verify=False)

    # Assert
    assert payload["sub"] == "12345678901"
    # Token está expirado mas foi aceito
    assert payload["exp"] < datetime.now(timezone.utc).timestamp()


# ============================================================================
# Testes: Fallback ao Unverified (sem JWKS e sem jwt_secret)
# ============================================================================

@pytest.mark.asyncio
async def test_jwt_decode_fallback_to_unverified_no_jwks_no_secret(valid_fernet_key):
    """
    Testa fallback para unverified decode quando:
    - Não há JWKS endpoint (localhost)
    - Não há jwt_secret configurado
    Deve logar warning e aceitar token.
    """
    # Arrange
    config = GovBrConfig(
        client_id="test_client_id",
        client_secret="test_secret",
        govbr_auth_url="https://localhost/authorize",
        govbr_token_url="https://localhost/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
        # jwt_secret NOT configured
    )

    integration = GovBrIntegration(config)
    token = create_hs256_token("any-secret", config.client_id)

    # Mock pyjwt.decode para evitar clock skew
    # Act & Assert
    with patch("govbr_auth.core.govbr.logger") as mock_logger:
        with patch("govbr_auth.core.govbr.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "12345678901",
                "email": "test@example.com",
            }
            payload = integration.jwt_payload_decode(token, verify=True)

            # Deve ter logado warning
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "JWT signature verification skipped" in warning_msg
            assert "no JWKS endpoint or jwt_secret configured" in warning_msg

    # Token foi aceito
    assert payload["sub"] == "12345678901"


# ============================================================================
# Testes: JWKS URL Resolution
# ============================================================================

@pytest.mark.asyncio
async def test_resolve_jwks_url_production(govbr_config_prod):
    """Testa resolução de JWKS URL para produção"""
    # Arrange
    integration = GovBrIntegration(govbr_config_prod)

    # Act
    jwks_url = integration._resolve_jwks_url()

    # Assert
    assert jwks_url == "https://sso.acesso.gov.br/jwk"


@pytest.mark.asyncio
async def test_resolve_jwks_url_staging(govbr_config_staging):
    """Testa resolução de JWKS URL para staging"""
    # Arrange
    integration = GovBrIntegration(govbr_config_staging)

    # Act
    jwks_url = integration._resolve_jwks_url()

    # Assert
    assert jwks_url == "https://sso.staging.acesso.gov.br/jwk"


@pytest.mark.asyncio
async def test_resolve_jwks_url_unknown_host(valid_fernet_key):
    """Testa resolução de JWKS URL para host desconhecido retorna None"""
    # Arrange
    config = GovBrConfig(
        client_id="test_client_id",
        client_secret="test_secret",
        govbr_auth_url="https://custom.example.com/authorize",
        govbr_token_url="https://custom.example.com/token",
        redirect_uri="https://localhost/callback",
        cript_verifier_secret=valid_fernet_key,
    )
    integration = GovBrIntegration(config)

    # Act
    jwks_url = integration._resolve_jwks_url()

    # Assert
    assert jwks_url is None

