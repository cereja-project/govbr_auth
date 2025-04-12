from pydantic import BaseModel, field_validator
from typing import Optional
import os
from dotenv import load_dotenv

__all__ = ["GovBrConfig"]

load_dotenv()


class GovBrConfig(BaseModel):
    """
    Configuração para integração com o Gov.br.
    Esta classe contém as informações necessárias para autenticação e autorização
    com o Gov.br, incluindo URLs, credenciais e parâmetros de configuração.

    :param client_id: ID do cliente registrado na plataforma Gov.br.
    :param client_secret: Segredo do cliente registrado na plataforma Gov.br.
    :param redirect_uri: URI de redirecionamento após a autenticação.
    :param cript_verifier_secret: Segredo usado para criptografar o código de verificação.
    :param auth_url: URL de autorização da plataforma Gov.br.
    :param token_url: URL de token da plataforma Gov.br.
    :param scope: Escopo de acesso solicitado (padrão: "openid profile email").
    :param response_type: Tipo de resposta esperado (padrão: "code").
    :param code_challenge_method: Método de desafio de código (padrão: "S256").
    :param jwt_secret: Segredo para assinatura de JWT (opcional).
    :param jwt_algorithm: Algoritmo de assinatura JWT (padrão: "HS256").
    :param jwt_expire_minutes: Tempo de expiração do JWT em minutos (padrão: 30).
    :param prefix: Prefixo para as rotas de autenticação (padrão: None).
    :param authorize_endpoint: Endpoint de autorização (padrão: None).
    :param authenticate_endpoint: Endpoint de autenticação (padrão: None).

    :raises ValueError: Se as variáveis obrigatórias não estiverem presentes no ambiente.
    :raises ValueError: Se a chave de criptografia não for válida.
    """
    client_id: str
    client_secret: str
    redirect_uri: str
    cript_verifier_secret: str

    # URLs da plataforma Gov.br
    auth_url: str
    token_url: str

    # Comportamento padrão do fluxo
    scope: str = "openid profile email"
    response_type: str = "code"
    code_challenge_method: str = "S256"

    # JWT
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # URLs internas da aplicação
    prefix: str = None
    authorize_endpoint: str = None
    authenticate_endpoint: str = None

    @field_validator("authorize_endpoint", "authenticate_endpoint", "prefix")
    def validate_endpoint(cls,
                          v):
        return v.strip("/ ")

    @field_validator("cript_verifier_secret")
    def validate_fernet_key(cls,
                            v):
        if len(v.encode()) != 44:
            raise ValueError(
                    "cript_verifier_secret precisa ser uma chave Fernet válida de 32 bytes base64 (44 caracteres)")
        return v

    @classmethod
    def from_env(cls):
        missing = [var for var in
                   ["GOVBR_CLIENT_ID", "GOVBR_CLIENT_SECRET", "GOVBR_REDIRECT_URI", "CRIPT_VERIFIER_SECRET"]
                   if not os.getenv(var)]
        if missing:
            raise ValueError(f"As seguintes variáveis obrigatórias estão faltando no ambiente: {', '.join(missing)}")

        return cls(
                client_id=os.getenv("GOVBR_CLIENT_ID"),
                client_secret=os.getenv("GOVBR_CLIENT_SECRET"),
                redirect_uri=os.getenv("GOVBR_REDIRECT_URI"),
                cript_verifier_secret=os.getenv("CRIPT_VERIFIER_SECRET"),
                auth_url=os.getenv("GOVBR_AUTH_URL", "https://sso.acesso.gov.br/authorize"),
                token_url=os.getenv("GOVBR_TOKEN_URL", "https://sso.acesso.gov.br/token"),
                scope=os.getenv("GOVBR_SCOPE", "openid"),
                response_type=os.getenv("GOVBR_RESPONSE_TYPE", "code"),
                code_challenge_method=os.getenv("GOVBR_CODE_CHALLENGE_METHOD", "S256"),
                jwt_secret=os.getenv("JWT_SECRET"),
                jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
                jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", 30)),
                auth_url_path=os.getenv("GOVBR_AUTH_URL_PATH", "/auth/govbr/url"),
                callback_url_path=os.getenv("GOVBR_CALLBACK_URL_PATH", "/auth/govbr/callback")
        )
