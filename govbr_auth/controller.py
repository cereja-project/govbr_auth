import asyncio
from typing import Callable, Optional

from govbr_auth.core.config import GovBrConfig
from pydantic import BaseModel
from govbr_auth import GovBrAuthorize
from govbr_auth import GovBrIntegration

__all__ = ["GovBrConnector"]


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
                 on_auth_success: Optional[Callable[[dict, object], object]] = None
                 ):
        """
        Inicializa a classe GovBrConnector com as configurações necessárias.
        :param config: Instância de GovBrConfig contendo as configurações necessárias para a autenticação.
        :param prefix: Prefixo para as rotas de autenticação (padrão: "/auth/govbr").
        :param authorize_endpoint: Endpoint para autorização (padrão: "authorize").
        :param authenticate_endpoint: Endpoint para autenticação (padrão: "authenticate").
        :param on_auth_success: Função de callback a ser chamada após a autenticação bem-sucedida.
        """
        self.config = config
        self.config.prefix = prefix.strip("/ ")
        self.config.authorize_endpoint = authorize_endpoint.strip("/ ")
        self.config.authenticate_endpoint = authenticate_endpoint.strip("/ ")
        self.on_auth_success = on_auth_success

    def init_fastapi(self,
                     app):
        from fastapi.routing import APIRouter
        from fastapi import Request

        router = APIRouter(prefix=f"/{self.config.prefix}", tags=["GovBR Auth"])

        @router.get(f"/{self.config.authorize_endpoint}")
        async def get_authorize_url():
            return GovBrAuthorize(self.config).build_authorize_url()

        @router.post(f"/{self.config.authenticate_endpoint}")
        async def govbr_callback(data: AuthenticationSchema,
                                 request: Request):
            integration = GovBrIntegration(self.config)
            result = await integration.async_exchange_code_for_token(data.code, data.state)
            if self.on_auth_success:
                result = self.on_auth_success(result, request)
                if asyncio.iscoroutine(result):
                    return await result
            return result

        app.include_router(router)

    def init_flask(self,
                   app):
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
