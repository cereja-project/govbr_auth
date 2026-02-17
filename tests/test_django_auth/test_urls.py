from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig

config = GovBrConfig(
        client_id="dummy_id",
        client_secret="dummy_secret",
        auth_url="https://sso.staging.acesso.gov.br/authorize",
        token_url="https://sso.staging.acesso.gov.br/token",
        redirect_uri="https://example.com/callback",
        cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso="
)

connector = GovBrConnector(config)
urlpatterns = connector.init_django()
