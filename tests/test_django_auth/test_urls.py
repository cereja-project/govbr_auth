from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig

config = GovBrConfig(
    client_id="dummy_id",
    client_secret="dummy_secret",
    govbr_auth_url="http://localhost/fake-govbr/authorize",
    govbr_token_url="http://localhost/fake-govbr/token",
    redirect_uri="http://localhost/callback",
    cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso=",
    use_fake=True,
)

connector = GovBrConnector(
    config,
    fake_jwt_secret="fake-govbr-test-secret-with-32-bytes",
)
urlpatterns = connector.init_django()
