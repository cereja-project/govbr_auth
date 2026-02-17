import asyncio
from typing import Callable, Optional
from urllib.parse import urlparse

from govbr_auth.core.config import GovBrConfig
from pydantic import BaseModel
from govbr_auth import GovBrAuthorize
from govbr_auth import GovBrIntegration

__all__ = ["GovBrConnector"]


def _is_fake_mode(config: GovBrConfig) -> bool:
    """
    Detecta se a configuração está usando o modo fake Gov.br baseado nas URLs.

    Args:
        config: Configuração do Gov.br

    Returns:
        True se estiver em modo fake, False caso contrário
    """
    # Verifica se as URLs apontam para localhost ou contêm "fake"
    auth_is_local = "localhost" in config.auth_url.lower() or "127.0.0.1" in config.auth_url
    token_is_local = "localhost" in config.token_url.lower() or "127.0.0.1" in config.token_url
    has_fake_in_url = "fake" in config.auth_url.lower() or "fake" in config.token_url.lower()

    return (auth_is_local and token_is_local) or has_fake_in_url


class AuthenticationSchema(BaseModel):
    """
    Schema para o corpo da requisição de autenticação.
    """
    code: str
    state: str


class AuthenticateResponseBody(BaseModel):
    """
    Schema para a resposta de autenticação.
    """
    access_token: str
    token_type: str
    expires_in: int
    id_token: str


class GovBrConnector:
    """
    Classe responsável por conectar o Gov.br com os frameworks FastAPI, Flask e Django.
    Ela fornece métodos para inicializar as rotas de autenticação e autorização do Gov.br
    em cada um desses frameworks.



    :type config: GovBrConfig
    :type prefix: str
    :type authorize_endpoint: str
    :type authenticate_endpoint: str
    """

    def __init__(self,
                 config: GovBrConfig,
                 prefix="/auth/govbr",
                 authorize_endpoint="authorize",
                 authenticate_endpoint="authenticate",
                 on_auth_success: Optional[Callable[[dict, object], object]] = None,
                 fake_users: Optional[dict] = None,
                 fake_jwt_secret: str = "fake-govbr-dev-secret"
                 ):
        """
        Inicializa a classe GovBrConnector com as configurações necessárias.

        :param config: Instância de GovBrConfig contendo as configurações necessárias para a autenticação.
        :param prefix: Prefixo para as rotas de autenticação (padrão: "/auth/govbr").
        :param authorize_endpoint: Endpoint para autorização (padrão: "authorize").
        :param authenticate_endpoint: Endpoint para autenticação (padrão: "authenticate").
        :param on_auth_success: Função de callback a ser chamada após a autenticação bem-sucedida.
        :param fake_users: Dicionário de usuários fake (opcional, apenas para modo fake).
        :param fake_jwt_secret: Chave secreta para JWT fake (opcional, apenas para modo fake).
        """
        self.config = config
        self.config.prefix = prefix.strip("/ ")
        self.config.authorize_endpoint = authorize_endpoint.strip("/ ")
        self.config.authenticate_endpoint = authenticate_endpoint.strip("/ ")
        self.on_auth_success = on_auth_success

        # Detecta se está em modo fake e inicializa o serviço
        self.is_fake_mode = _is_fake_mode(config)
        self.fake_service = None

        if self.is_fake_mode:
            from govbr_auth.fake_govbr import FakeGovBrService, create_default_fake_users

            users = fake_users if fake_users is not None else create_default_fake_users()
            self.fake_service = FakeGovBrService(
                users=users,
                jwt_secret=fake_jwt_secret,
                client_id=config.client_id
            )

            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🧪 Modo FAKE Gov.br ativado - Endpoints fake serão registrados automaticamente")

    def init_fastapi(self, app):
        from fastapi.routing import APIRouter
        from fastapi import Request

        router = APIRouter(prefix=f"/{self.config.prefix}", tags=["GovBR Auth"])

        @router.get(f"/{self.config.authorize_endpoint}")
        async def get_authorize_url():
            return GovBrAuthorize(self.config).build_authorize_url()

        @router.post(f"/{self.config.authenticate_endpoint}")
        async def govbr_callback(data: AuthenticationSchema, request: Request):
            integration = GovBrIntegration(self.config)
            result = await integration.async_exchange_code_for_token(data.code, data.state)
            if self.on_auth_success:
                result = self.on_auth_success(result, request)
                if asyncio.iscoroutine(result):
                    return await result
            return result

        app.include_router(router)

        # Se estiver em modo fake, registra os endpoints fake
        if self.is_fake_mode and self.fake_service:
            from fastapi import Form, HTTPException
            from fastapi.responses import HTMLResponse, RedirectResponse
            from govbr_auth.fake_govbr import render_fake_login_page, process_fake_login, AuthorizationRequest

            # Extrai o path base da URL fake
            parsed_url = urlparse(self.config.auth_url)
            # Remove o último componente do path (/authorize) para obter o prefixo
            path_parts = parsed_url.path.rstrip('/').split('/')
            auth_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''
            # Garante que sempre comece com /
            if not auth_path.startswith('/'):
                auth_path = '/' + auth_path if auth_path else ''

            fake_router = APIRouter(prefix=auth_path, tags=["Fake Gov.br (Dev Only)"])

            @fake_router.get("/authorize", response_class=HTMLResponse)
            async def fake_authorize(
                response_type: str,
                client_id: str,
                scope: str,
                redirect_uri: str,
                state: str,
                nonce: str,
                code_challenge: str,
                code_challenge_method: str
            ):
                """Simula o endpoint /authorize do Gov.br"""
                auth_request = AuthorizationRequest(
                    response_type=response_type,
                    client_id=client_id,
                    scope=scope,
                    redirect_uri=redirect_uri,
                    state=state,
                    nonce=nonce,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method
                )
                html, _ = render_fake_login_page(self.fake_service, auth_request)
                return html

            @fake_router.post("/login")
            async def fake_login(
                request_id: str = Form(...),
                email: str = Form(...),
                password: str = Form(...)
            ):
                """Processa o login fake"""
                try:
                    redirect_url = process_fake_login(
                        service=self.fake_service,
                        request_id=request_id,
                        email=email,
                        cpf=password
                    )
                    return RedirectResponse(url=redirect_url, status_code=302)
                except ValueError as e:
                    raise HTTPException(status_code=401, detail=str(e))

            @fake_router.post("/token")
            async def fake_token(
                code: str = Form(...),
                code_verifier: str = Form(...),
                redirect_uri: str = Form(...),
                client_id: str = Form(None),
                grant_type: str = Form("authorization_code")
            ):
                """Simula o endpoint /token do Gov.br"""
                try:
                    return self.fake_service.exchange_code_for_token(
                        code=code,
                        code_verifier=code_verifier,
                        redirect_uri=redirect_uri,
                        client_id=client_id
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

            @fake_router.get("/users")
            async def list_fake_users():
                """Lista os usuários disponíveis para teste"""
                users_list = []
                for cpf, user in self.fake_service.users.items():
                    users_list.append({
                        "cpf": cpf,
                        "nome": user.nome,
                        "email": user.email,
                        "senha": cpf
                    })
                return {"usuarios_de_teste": users_list}

            app.include_router(fake_router)

    def init_flask(self, app):
        from flask import Blueprint, request, jsonify

        bp = Blueprint('govbr_auth', __name__, url_prefix=f"/{self.config.prefix}")

        @bp.route(f'/{self.config.authorize_endpoint}', methods=['GET'])
        def get_authorize_url():
            authorize = GovBrAuthorize(self.config)
            return jsonify(authorize.build_authorize_url())

        @bp.route(f'/{self.config.authenticate_endpoint}', methods=['POST'])
        def govbr_callback():
            code = request.args.get("code")
            state = request.args.get("state")
            if not code or not state:
                return jsonify({"error": "Missing 'code' or 'state' parameter"}), 400
            integration = GovBrIntegration(self.config)
            result = integration.exchange_code_for_token_sync(code, state)
            if self.on_auth_success:
                return self.on_auth_success(result, request)
            else:
                return jsonify(result)

        app.register_blueprint(bp)

        # Se estiver em modo fake, registra os endpoints fake
        if self.is_fake_mode and self.fake_service:
            from flask import redirect
            from govbr_auth.fake_govbr import render_fake_login_page, process_fake_login, AuthorizationRequest

            # Extrai o path base da URL fake
            auth_path = self.config.auth_url.split('://')[-1]
            auth_path = '/' + '/'.join(auth_path.split('/')[1:-1])

            fake_bp = Blueprint('fake_govbr', __name__, url_prefix=auth_path)

            @fake_bp.route("/authorize")
            def fake_authorize():
                """Simula o endpoint /authorize do Gov.br"""
                auth_request = AuthorizationRequest(
                    response_type=request.args.get("response_type"),
                    client_id=request.args.get("client_id"),
                    scope=request.args.get("scope"),
                    redirect_uri=request.args.get("redirect_uri"),
                    state=request.args.get("state"),
                    nonce=request.args.get("nonce"),
                    code_challenge=request.args.get("code_challenge"),
                    code_challenge_method=request.args.get("code_challenge_method")
                )
                html, _ = render_fake_login_page(self.fake_service, auth_request)
                return html

            @fake_bp.route("/login", methods=["POST"])
            def fake_login():
                """Processa o login fake"""
                try:
                    redirect_url = process_fake_login(
                        service=self.fake_service,
                        request_id=request.form.get("request_id"),
                        email=request.form.get("email"),
                        cpf=request.form.get("password")
                    )
                    return redirect(redirect_url)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 401

            @fake_bp.route("/token", methods=["POST"])
            def fake_token():
                """Simula o endpoint /token do Gov.br"""
                try:
                    token_data = self.fake_service.exchange_code_for_token(
                        code=request.form.get("code"),
                        code_verifier=request.form.get("code_verifier"),
                        redirect_uri=request.form.get("redirect_uri"),
                        client_id=request.form.get("client_id")
                    )
                    return jsonify(token_data)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            @fake_bp.route("/users")
            def list_fake_users():
                """Lista os usuários disponíveis para teste"""
                users_list = []
                for cpf, user in self.fake_service.users.items():
                    users_list.append({
                        "cpf": cpf,
                        "nome": user.nome,
                        "email": user.email,
                        "senha": cpf
                    })
                return jsonify({"usuarios_de_teste": users_list})

            app.register_blueprint(fake_bp)

    def init_django(self):
        from django.urls import path
        from django.http import JsonResponse
        from django.views import View
        from django.urls import include
        import asyncio

        class GovBrUrlView(View):
            config = None

            def dispatch(self,
                         request,
                         *args,
                         **kwargs):
                self.config = kwargs.pop('config', None)
                return super().dispatch(request, *args, **kwargs)

            def get(self,
                    request):
                return JsonResponse(GovBrAuthorize(self.config).build_authorize_url())

        class GovBrCallbackView(View):
            config = None
            on_auth_success = None

            def dispatch(self,
                         request,
                         *args,
                         **kwargs):
                self.config = kwargs.pop('config', None)
                self.on_auth_success = kwargs.pop('on_auth_success', None)
                return super().dispatch(request, *args, **kwargs)

            def post(self,
                     request):
                code = request.POST.get('code')
                state = request.POST.get('state')
                if not code or not state:
                    return JsonResponse({"error": "Missing 'code' or 'state' parameter"}, status=400)
                result = asyncio.run(GovBrIntegration(self.config).async_exchange_code_for_token(code, state))
                if self.on_auth_success:
                    return self.on_auth_success(result, request)
                else:
                    return JsonResponse(result)

        urls_patterns = [
            path(self.config.authorize_endpoint, GovBrUrlView.as_view(), {'config': self.config},
                 name='govbr-auth-url'),
            path(self.config.authenticate_endpoint, GovBrCallbackView.as_view(), {'config':          self.config,
                                                                                  "on_auth_success": self.on_auth_success},
                 name='govbr-auth-callback'),
        ]

        return [path(f"{self.config.prefix}/", include(urls_patterns))]

