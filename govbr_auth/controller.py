from govbr_auth.core.config import GovBrConfig

__all__ = ["GovBrConnector"]


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
                 authenticate_endpoint="authenticate"
                 ):
        """
        Inicializa a classe GovBrConnector com as configurações necessárias.
        :param config: Instância de GovBrConfig contendo as configurações necessárias para a autenticação.
        :param prefix: Prefixo para as rotas de autenticação (padrão: "/auth/govbr").
        :param authorize_endpoint: Endpoint para autorização (padrão: "authorize").
        :param authenticate_endpoint: Endpoint para autenticação (padrão: "authenticate").
        """
        self.config = config
        self.config.prefix = prefix.strip("/ ")
        self.config.authorize_endpoint = authorize_endpoint.strip("/ ")
        self.config.authenticate_endpoint = authenticate_endpoint.strip("/ ")

    def init_fastapi(self,
                     app):
        from fastapi import FastAPI
        from govbr_auth.fastapi_ext.routes import get_router
        app.include_router(get_router(self.config))

    def init_flask(self,
                   app):
        from flask import Flask
        from govbr_auth.flask_ext.routes import get_blueprint
        app.register_blueprint(get_blueprint(self.config))

    def init_django(self):
        from django.urls import path, include
        from govbr_auth.django_ext import urls
        return [path(f"{self.config.prefix}/", include(urls.get_urlpatterns(self.config)))]
