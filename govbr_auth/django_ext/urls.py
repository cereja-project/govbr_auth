from django.urls import path

from govbr_auth.core import GovBrConfig
from govbr_auth.django_ext.views import GovBrUrlView, GovBrCallbackView


def get_urlpatterns(config: GovBrConfig):
    """
    Gera as URLs para o Django com base na configuração do GovBr.

    :param config: Instância de GovBrConfig contendo as configurações necessárias para a autenticação.
    :return: Lista de URLs do Django.
    """
    urlpatterns = [
        path(config.authorize_endpoint, GovBrUrlView.as_view(), name='govbr-auth-url'),
        path(config.authenticate_endpoint, GovBrCallbackView.as_view(), name='govbr-auth-callback'),
    ]
    return urlpatterns
