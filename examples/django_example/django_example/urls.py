"""URL configuration for the govbr-auth Django example."""

import os

from django.urls import path

from govbr_auth import GovBrConfig, GovBrConnector

from django_example.views import handle_auth_success, home


def build_config() -> GovBrConfig:
    """Build a fake local configuration or load the real service from the environment."""
    use_fake = os.getenv("USE_FAKE_GOVBR", "true").lower() in {"1", "true", "yes"}
    if not use_fake:
        return GovBrConfig.from_env()

    return GovBrConfig(
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        redirect_uri="http://127.0.0.1:8000/auth/govbr/authenticate",
        cript_verifier_secret="Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=",
        govbr_auth_url="http://127.0.0.1:8000/fake-govbr/authorize",
        govbr_token_url="http://127.0.0.1:8000/fake-govbr/token",
        use_fake=True,
    )


connector = GovBrConnector(config=build_config(), on_auth_success=handle_auth_success)

urlpatterns = [
    path("", home, name="home"),
    *connector.init_django(),
]
