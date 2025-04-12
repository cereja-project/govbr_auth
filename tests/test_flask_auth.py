import pytest
from flask import Flask

from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig


def create_app():
    config = GovBrConfig(
            client_id="dummy_id",
            client_secret="dummy_secret",
            auth_url="https://localhost/authorize",
            token_url="https://localhost/token",
            redirect_uri="https://localhost/callback",
            cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso=",
    )
    app = Flask(__name__)
    controller = GovBrConnector(config,
                                prefix="/auth",
                                authorize_endpoint="/govbr/authorize",
                                authenticate_endpoint="/govbr/callback",
                                )
    controller.init_flask(app)
    return app


@pytest.fixture
def client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_get_url(client):
    response = client.get("/auth/govbr/authorize")
    assert response.status_code == 200
    assert b"url" in response.data or b"error" in response.data
