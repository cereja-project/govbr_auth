import base64
import secrets
import hashlib
from datetime import datetime, timedelta
from pydantic import BaseModel
import jwt
import logging
logger = logging.getLogger(__name__)


_SESSION_DATA = {}


class AuthorizationRequest(BaseModel):
    response_type: str
    client_id: str
    scope: str
    redirect_uri: str
    nonce: str
    state: str
    code_challenge: str
    code_challenge_method: str


GOVBR_LOGIN_PAGE_FAKE = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Gov.br (FAKE)</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #ff6b35 0%, #f7931e 50%, #ff8c42 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .login-container {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(255, 107, 53, 0.3);
            width: 100%;
            max-width: 420px;
            padding: 40px;
            animation: fadeIn 0.5s ease-in;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .fake-badge {{
            background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-size: 12px;
            font-weight: bold;
            text-align: center;
            margin-bottom: 20px;
            display: inline-block;
            box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo h1 {{
            color: #ff6b35;
            font-size: 36px;
            margin-bottom: 5px;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(255, 107, 53, 0.1);
        }}
        .logo p {{
            color: #666;
            font-size: 14px;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            color: #333;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 14px;
        }}
        input {{
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.3s;
        }}
        input:focus {{
            outline: none;
            border-color: #ff6b35;
            box-shadow: 0 0 0 3px rgba(255, 107, 53, 0.1);
        }}
        .btn {{
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3);
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(255, 107, 53, 0.4);
        }}
        .info {{
            margin-top: 25px;
            padding: 20px;
            background: linear-gradient(135deg, #fff5f0 0%, #ffe8dc 100%);
            border-left: 4px solid #ff6b35;
            border-radius: 8px;
        }}
        .info h3 {{
            color: #ff6b35;
            font-size: 14px;
            margin-bottom: 12px;
            font-weight: 700;
        }}
        .info p {{
            color: #555;
            font-size: 12px;
            line-height: 1.6;
            margin-bottom: 5px;
        }}
        .error {{
            background: #fee;
            border-left-color: #c00;
            color: #c00;
        }}
    </style>
</head>
<body>
    <div class="login-container">            
        <div class="logo">
            <h1>gov.br</h1>
            <p>Acesso Simplificado</p>
        </div>
        
        <form method="POST" action="/fake-govbr/login">
            <input type="hidden" name="request_id" value="">
            
            <div class="form-group">
                <label for="email">E-mail:</label>
                <input type="email" id="email" name="email" placeholder="seuemail@example.com" required>
            </div>
            
            <div class="form-group">
                <label for="password">CPF (senha):</label>
                <input type="text" id="password" name="password" placeholder="Digite o CPF (11 dígitos)" required>
            </div>
            
            <button type="submit" class="btn">Entrar</button>
        </form>
    </div>
</body>
</html>
"""

class FakeUserData(BaseModel):
    """
    Schema para dados de um usuário fake no sistema.

    Args:
        cpf: CPF do usuário (11 dígitos, usado como senha no fake).
        nome: Nome completo do usuário.
        email: E-mail do usuário.
        picture: URL da foto do usuário (opcional).
    """
    cpf: str
    nome: str
    email: str
    picture: str = "https://www.gov.br/++theme++padrao_govbr/img/govbr-logo-large.png"


class FakeGovBrService:
    """
    Serviço que simula o comportamento do Gov.br para desenvolvimento.

    Mantém sessões e autorizações em memória, sem necessidade de banco de dados.
    Simula o fluxo OAuth 2.0 com PKCE do Gov.br real.

    Args:
        users: Dicionário de usuários válidos (chave=CPF, valor=FakeUserData).
        session_ttl: Tempo de vida da sessão em segundos (padrão: 600 = 10 minutos).
        jwt_secret: Chave secreta para assinar o id_token.
        client_id: ID do cliente OAuth (deve coincidir com a config).
    """

    def __init__(self,
                 users: dict[str, FakeUserData],
                 session_ttl: int = 600,
                 jwt_secret: str = "fake-govbr-secret-key-dev-only",
                 client_id: str = "fake-client-id"):
        self.users = users
        self.session_ttl = session_ttl
        self.jwt_secret = jwt_secret
        self.client_id = client_id
        self._sessions = {}
        self._authorization_codes = {}
        logger.info(f"FakeGovBrService inicializado com {len(users)} usuários")

    def create_session(self,
                      state: str,
                      code_challenge: str,
                      redirect_uri: str,
                      nonce: str,
                      scope: str = "openid profile email") -> str:
        """
        Cria uma sessão temporária para armazenar os parâmetros OAuth.

        Args:
            state: State criptografado do OAuth.
            code_challenge: Desafio PKCE.
            redirect_uri: URI de redirecionamento.
            nonce: Nonce para validação.
            scope: Escopos solicitados.

        Returns:
            request_id: ID único da sessão criada.
        """
        request_id = secrets.token_urlsafe(32)
        session_data = {
            "state": state,
            "code_challenge": code_challenge,
            "redirect_uri": redirect_uri,
            "nonce": nonce,
            "scope": scope,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(seconds=self.session_ttl)
        }
        self._sessions[request_id] = session_data
        logger.debug(f"Sessão criada: {request_id}")
        return request_id

    def get_session(self, request_id: str) -> dict:
        """
        Recupera uma sessão pelo ID.

        Args:
            request_id: ID da sessão.

        Returns:
            Dados da sessão.

        Raises:
            ValueError: Se a sessão não existir ou estiver expirada.
        """
        if request_id not in self._sessions:
            raise ValueError("Sessão não encontrada ou expirada")

        session = self._sessions[request_id]

        if datetime.now() > session["expires_at"]:
            del self._sessions[request_id]
            raise ValueError("Sessão expirada")

        return session

    def authenticate_user(self,
                         request_id: str,
                         email: str,
                         cpf: str) -> str:
        """
        Autentica um usuário e gera o código de autorização.

        Args:
            request_id: ID da sessão OAuth.
            email: E-mail fornecido pelo usuário.
            cpf: CPF fornecido como senha.

        Returns:
            URL de redirecionamento com code e state.

        Raises:
            ValueError: Se credenciais inválidas ou sessão inválida.
        """
        # Valida a sessão
        session = self.get_session(request_id)

        # Remove formatação do CPF
        cpf_clean = cpf.replace(".", "").replace("-", "").strip()

        # Valida se o usuário existe
        if cpf_clean not in self.users:
            raise ValueError("CPF não encontrado")

        user = self.users[cpf_clean]

        # Valida o e-mail
        if user.email != email:
            raise ValueError("E-mail não corresponde ao CPF informado")

        # Gera o código de autorização
        auth_code = secrets.token_urlsafe(32)

        # Armazena o código com os dados necessários
        self._authorization_codes[auth_code] = {
            "user": user,
            "code_challenge": session["code_challenge"],
            "redirect_uri": session["redirect_uri"],
            "nonce": session["nonce"],
            "scope": session["scope"],
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(seconds=300)  # Code expira em 5 min
        }

        # Remove a sessão (já foi usada)
        del self._sessions[request_id]

        # Monta a URL de redirecionamento
        redirect_url = f"{session['redirect_uri']}?code={auth_code}&state={session['state']}"

        logger.info(f"Usuário autenticado: {user.email}")
        return redirect_url

    def exchange_code_for_token(self,
                               code: str,
                               code_verifier: str,
                               redirect_uri: str,
                               client_id: str = None) -> dict:
        """
        Troca o código de autorização por tokens (simulando o endpoint /token do Gov.br).

        Args:
            code: Código de autorização.
            code_verifier: Verificador PKCE.
            redirect_uri: URI de redirecionamento (deve ser a mesma).
            client_id: ID do cliente (opcional, para validação).

        Returns:
            Dicionário com access_token, id_token, etc.

        Raises:
            ValueError: Se código inválido ou code_verifier não corresponder.
        """
        if code not in self._authorization_codes:
            raise ValueError("Código de autorização inválido ou expirado")

        auth_data = self._authorization_codes[code]

        # Valida expiração
        if datetime.now() > auth_data["expires_at"]:
            del self._authorization_codes[code]
            raise ValueError("Código de autorização expirado")

        # Valida redirect_uri
        if auth_data["redirect_uri"] != redirect_uri:
            raise ValueError("redirect_uri não corresponde")

        # Valida code_verifier usando PKCE (S256)
        code_challenge_calculated = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').replace('=', '')

        if auth_data["code_challenge"] != code_challenge_calculated:
            raise ValueError("code_verifier inválido")

        user = auth_data["user"]

        # Gera o access_token (fake)
        access_token = secrets.token_urlsafe(32)

        # Gera o id_token (JWT)
        now = datetime.now()
        id_token_payload = {
            "sub": user.cpf,
            "name": user.nome,
            "email": user.email,
            "email_verified": True,
            "picture": user.picture,
            "iss": "https://sso.staging.acesso.gov.br",
            "aud": client_id or self.client_id,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": auth_data["nonce"],
            "amr": ["passwd"],
            "cpf": user.cpf
        }

        id_token = jwt.encode(
            id_token_payload,
            self.jwt_secret,
            algorithm="HS256"
        )

        # Remove o código (já foi usado)
        del self._authorization_codes[code]

        logger.info(f"Token gerado para usuário: {user.email}")

        # Retorna no formato Gov.br
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": id_token,
            "scope": auth_data["scope"]
        }

    def cleanup_expired(self):
        """
        Remove sessões e códigos expirados da memória.
        Deve ser chamado periodicamente para evitar vazamento de memória.
        """
        now = datetime.now()

        # Limpa sessões expiradas
        expired_sessions = [
            sid for sid, session in self._sessions.items()
            if now > session["expires_at"]
        ]
        for sid in expired_sessions:
            del self._sessions[sid]

        # Limpa códigos expirados
        expired_codes = [
            code for code, auth in self._authorization_codes.items()
            if now > auth["expires_at"]
        ]
        for code in expired_codes:
            del self._authorization_codes[code]

        if expired_sessions or expired_codes:
            logger.debug(f"Limpeza: {len(expired_sessions)} sessões e {len(expired_codes)} códigos removidos")


# Funções auxiliares para integração com frameworks
def render_fake_login_page(service: FakeGovBrService,
                          auth_request: AuthorizationRequest) -> tuple[str, str]:
    """
    Renderiza a página de login fake e cria a sessão OAuth.

    Args:
        service: Instância do FakeGovBrService.
        auth_request: Dados da requisição de autorização.

    Returns:
        Tupla com (HTML da página, request_id da sessão).
    """
    request_id = service.create_session(
        state=auth_request.state,
        code_challenge=auth_request.code_challenge,
        redirect_uri=auth_request.redirect_uri,
        nonce=auth_request.nonce,
        scope=auth_request.scope
    )

    # Injeta o request_id no HTML
    html = GOVBR_LOGIN_PAGE_FAKE.replace('value=""', f'value="{request_id}"')

    return html, request_id


def process_fake_login(service: FakeGovBrService,
                      request_id: str,
                      email: str,
                      cpf: str) -> str:
    """
    Processa o login fake e retorna a URL de redirecionamento.

    Args:
        service: Instância do FakeGovBrService.
        request_id: ID da sessão OAuth.
        email: E-mail fornecido pelo usuário.
        cpf: CPF fornecido como senha.

    Returns:
        URL de redirecionamento com code e state.

    Raises:
        ValueError: Se credenciais inválidas.
    """
    return service.authenticate_user(request_id, email, cpf)


def create_default_fake_users() -> dict[str, FakeUserData]:
    """
    Cria um conjunto de usuários fake padrão para desenvolvimento.

    Returns:
        Dicionário de usuários (chave=CPF).
    """
    return {
        "12345678901": FakeUserData(
            cpf="12345678901",
            nome="João da Silva",
            email="joao.silva@example.com"
        ),
        "98765432100": FakeUserData(
            cpf="98765432100",
            nome="Maria Oliveira",
            email="maria.oliveira@example.com"
        ),
        "11122233344": FakeUserData(
            cpf="11122233344",
            nome="José Santos",
            email="jose.santos@example.com"
        )
    }
