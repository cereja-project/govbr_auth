"""Behavior and routing tests for the Django adapter."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory
from django.urls import resolve

from govbr_auth.controller import GovBrConnector
from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrAuthenticationError
from tests.test_django_auth.test_urls import config


def build_config(
    *,
    redirect_uri: str = "http://localhost/callback",
    govbr_auth_url: str = "http://localhost/fake-govbr/authorize",
    govbr_token_url: str = "http://localhost/fake-govbr/token",
) -> GovBrConfig:
    """Build an isolated fake configuration for route tests."""
    return GovBrConfig(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri=redirect_uri,
        cript_verifier_secret="GN6DdLRiwO7ylIR7PEKXN0xtPnagRqwI8T6wXxI5cso=",
        govbr_auth_url=govbr_auth_url,
        govbr_token_url=govbr_token_url,
        use_fake=True,
    )


def extract_request_id(response: HttpResponse) -> str:
    """Extract the fake OAuth request identifier from an HTML response."""
    match = re.search(
        r'name="request_id" value="([^"]+)"',
        response.content.decode(),
    )
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize("method", ["get", "post"])
def test_callback_exchanges_code_from_get_and_post(client, mocker, method):
    integration_class = mocker.patch(
        "govbr_auth.controller.GovBrIntegration",
        autospec=True,
    )
    integration_class.return_value.exchange_code_for_token_sync.return_value = {
        "token": {"access_token": "access-token"},
        "id_token_decoded": {"sub": "12345678901"},
    }

    response = getattr(client, method)(
        "/callback",
        data={"code": "authorization-code", "state": "encrypted-state"},
    )

    assert response.status_code == 200
    assert response.json()["id_token_decoded"]["sub"] == "12345678901"
    integration_class.assert_called_once_with(config)
    integration_class.return_value.exchange_code_for_token_sync.assert_called_once_with(
        "authorization-code",
        "encrypted-state",
    )


def test_callback_without_required_parameters_returns_400(client, mocker):
    integration_class = mocker.patch(
        "govbr_auth.controller.GovBrIntegration",
        autospec=True,
    )

    response = client.get("/callback", data={"code": "authorization-code"})

    assert response.status_code == 400
    assert response.json() == {"error": "Missing 'code' or 'state' parameter"}
    integration_class.assert_not_called()


def test_callback_authentication_failure_returns_401(client, mocker):
    integration_class = mocker.patch(
        "govbr_auth.controller.GovBrIntegration",
        autospec=True,
    )
    integration_class.return_value.exchange_code_for_token_sync.side_effect = (
        GovBrAuthenticationError("invalid authorization code")
    )

    response = client.get(
        "/callback",
        data={"code": "invalid-code", "state": "encrypted-state"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid authorization code"}


def test_callback_invalid_encrypted_state_returns_401(client, mocker):
    integration_class = mocker.patch(
        "govbr_auth.controller.GovBrIntegration",
        autospec=True,
    )
    integration_class.return_value.exchange_code_for_token_sync.side_effect = ValueError(
        "Invalid or missing code_verifier"
    )

    response = client.get(
        "/callback",
        data={"code": "authorization-code", "state": "invalid-state"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Invalid or missing code_verifier"}


def test_callback_returns_on_auth_success_response(mocker):
    success_callback = mocker.Mock(
        return_value=JsonResponse({"authenticated": True}),
    )
    connector = GovBrConnector(
        build_config(),
        on_auth_success=success_callback,
    )
    patterns = tuple(connector.init_django())
    match = resolve("/callback", urlconf=patterns)
    request = RequestFactory().get(
        "/callback",
        data={"code": "authorization-code", "state": "encrypted-state"},
    )
    integration_class = mocker.patch(
        "govbr_auth.controller.GovBrIntegration",
        autospec=True,
    )
    result = {"id_token_decoded": {"sub": "12345678901"}}
    integration_class.return_value.exchange_code_for_token_sync.return_value = result

    response = match.func(request, **match.kwargs)

    assert response.status_code == 200
    assert json.loads(response.content) == {"authenticated": True}
    success_callback.assert_called_once_with(result, request)


@pytest.mark.parametrize(
    ("redirect_uri", "request_path", "expected_name"),
    [
        ("https://app.example/callback", "/callback", "govbr-auth-redirect-callback"),
        (
            "https://app.example/oauth/callback/",
            "/oauth/callback/",
            "govbr-auth-redirect-callback",
        ),
        (
            "https://app.example/other/authenticate",
            "/other/authenticate",
            "govbr-auth-redirect-callback",
        ),
        ("https://app.example/", "/", "govbr-auth-redirect-callback"),
        (
            "https://app.example/auth/govbr/authenticate",
            "/auth/govbr/authenticate",
            "govbr-auth-callback",
        ),
    ],
)
def test_callback_uses_complete_configured_redirect_path(
    redirect_uri,
    request_path,
    expected_name,
):
    connector = GovBrConnector(build_config(redirect_uri=redirect_uri))
    patterns = tuple(connector.init_django())

    match = resolve(request_path, urlconf=patterns)

    assert match.url_name == expected_name


@pytest.mark.parametrize(
    ("request_path", "expected_name"),
    [
        ("/custom/oauth/authorize", "fake-govbr-authorize"),
        ("/custom/oauth/login", "fake-govbr-login"),
        ("/custom/oauth/users", "fake-govbr-users"),
        ("/custom/token/exchange", "fake-govbr-token"),
    ],
)
def test_fake_routes_respect_configured_paths_and_ignore_query(
    request_path,
    expected_name,
):
    connector = GovBrConnector(
        build_config(
            govbr_auth_url="http://localhost/custom/oauth/authorize?tenant=one",
            govbr_token_url="http://localhost/custom/token/exchange?tenant=one",
        )
    )
    patterns = tuple(connector.init_django())

    match = resolve(request_path, urlconf=patterns)

    assert match.url_name == expected_name


@pytest.mark.parametrize(
    ("request_path", "expected_name"),
    [
        ("/authorize", "fake-govbr-authorize"),
        ("/login", "fake-govbr-login"),
        ("/users", "fake-govbr-users"),
        ("/token", "fake-govbr-token"),
    ],
)
def test_fake_routes_support_endpoints_at_site_root(request_path, expected_name):
    connector = GovBrConnector(
        build_config(
            govbr_auth_url="http://localhost/authorize",
            govbr_token_url="http://localhost/token",
        )
    )
    patterns = tuple(connector.init_django())

    match = resolve(request_path, urlconf=patterns)

    assert match.url_name == expected_name


def test_fake_authorize_renders_configured_login_action():
    connector = GovBrConnector(
        build_config(
            govbr_auth_url="http://localhost/custom/oauth/authorize",
            govbr_token_url="http://localhost/custom/oauth/token",
        )
    )
    patterns = tuple(connector.init_django())
    match = resolve("/custom/oauth/authorize", urlconf=patterns)
    request = RequestFactory().get("/custom/oauth/authorize")

    response = match.func(request, **match.kwargs)

    assert response.status_code == 200
    assert 'action="/custom/oauth/login"' in response.content.decode()


def test_fake_authorize_with_partial_parameters_returns_400(client):
    response = client.get(
        "/fake-govbr/authorize",
        data={"state": "encrypted-state"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid authorization parameters"}


def test_fake_users_returns_available_accounts(client):
    response = client.get("/fake-govbr/users")

    assert response.status_code == 200
    users = response.json()["usuarios_de_teste"]
    assert len(users) == 3
    assert users[0] == {
        "cpf": "12345678901",
        "nome": "João da Silva",
        "email": "joao.silva@example.com",
        "senha": "12345678901",
    }


def test_fake_login_redirects_authenticated_user(client):
    authorize_response = client.get("/fake-govbr/authorize")
    request_id = extract_request_id(authorize_response)

    response = client.post(
        "/fake-govbr/login",
        data={
            "request_id": request_id,
            "email": "joao.silva@example.com",
            "password": "12345678901",
        },
    )

    assert response.status_code == 302
    redirect = urlparse(response["Location"])
    assert redirect.path == "/callback"
    assert set(parse_qs(redirect.query)) == {"code", "state"}


def test_fake_login_without_password_returns_400(client):
    response = client.post(
        "/fake-govbr/login",
        data={"request_id": "request-id", "email": "joao.silva@example.com"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Missing required fields: password"}


def test_fake_login_with_invalid_credentials_returns_401(client):
    authorize_response = client.get("/fake-govbr/authorize")
    request_id = extract_request_id(authorize_response)

    response = client.post(
        "/fake-govbr/login",
        data={
            "request_id": request_id,
            "email": "wrong@example.com",
            "password": "12345678901",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"error": "E-mail não corresponde ao CPF informado"}


def test_fake_token_exchanges_valid_authorization_code(client):
    authorize_response = client.get("/fake-govbr/authorize")
    request_id = extract_request_id(authorize_response)
    login_response = client.post(
        "/fake-govbr/login",
        data={
            "request_id": request_id,
            "email": "joao.silva@example.com",
            "password": "12345678901",
        },
    )
    callback_parameters = parse_qs(urlparse(login_response["Location"]).query)
    state = callback_parameters["state"][0]
    code_verifier = Fernet(config.cript_verifier_secret.encode()).decrypt(
        state.encode()
    ).decode()

    response = client.post(
        "/fake-govbr/token",
        data={
            "code": callback_parameters["code"][0],
            "code_verifier": code_verifier,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["scope"] == "openid profile email"


def test_fake_token_without_code_verifier_returns_400(client):
    response = client.post(
        "/fake-govbr/token",
        data={"code": "authorization-code", "redirect_uri": config.redirect_uri},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Missing required fields: code_verifier"}
