"""Freeze the public v1 contract of the framework-independent fake provider."""

import subprocess
import sys
from dataclasses import fields
from pathlib import Path

from govbr_auth.fake import (
    FakeAuthorizationRedirect,
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeCredentialAuthenticator,
    FakeGovBrEndpoints,
    FakeGovBrProvider,
    FakeGovSimulator,
    FakeLoginCredential,
    FakeOAuthError,
    FakeUserRepository,
    InMemoryFakeUserRepository,
    JsonFakeUserRepository,
    FakeTokenRequest,
    FakeTokenResponse,
    create_fake_gov_simulator,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_fake_provider_request_field_names_are_stable() -> None:
    assert tuple(field.name for field in fields(FakeAuthorizationRequest)) == (
        "response_type",
        "client_id",
        "redirect_uri",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
    )
    assert tuple(field.name for field in fields(FakeClientCredentials)) == (
        "client_id",
        "client_secret",
    )
    assert tuple(field.name for field in fields(FakeTokenRequest)) == (
        "grant_type",
        "code",
        "redirect_uri",
        "code_verifier",
    )


def test_fake_provider_result_field_names_are_stable() -> None:
    assert tuple(field.name for field in fields(FakeAuthorizationSession)) == (
        "request",
        "users",
    )
    assert tuple(field.name for field in fields(FakeAuthorizationRedirect)) == (
        "redirect_uri",
        "code",
    )
    assert tuple(field.name for field in fields(FakeTokenResponse)) == (
        "access_token",
        "token_type",
        "expires_in",
        "id_token",
        "scope",
    )


def test_fake_token_response_preserves_bearer_casing() -> None:
    assert FakeTokenResponse.__dataclass_fields__["token_type"].default == "Bearer"


def test_fake_package_exports_provider_contract_without_top_level_export() -> None:
    import govbr_auth
    import govbr_auth.fake as fake

    assert fake.FakeGovBrProvider is FakeGovBrProvider
    assert fake.FakeOAuthError is FakeOAuthError
    assert not hasattr(govbr_auth, "FakeGovBrProvider")


def test_fake_package_exports_credential_contract() -> None:
    import govbr_auth.fake as fake

    assert fake.FakeCredentialAuthenticator is FakeCredentialAuthenticator
    assert fake.FakeUserRepository is FakeUserRepository
    assert fake.InMemoryFakeUserRepository is InMemoryFakeUserRepository
    assert fake.JsonFakeUserRepository is JsonFakeUserRepository
    assert "FakeCredentialAuthenticator" in fake.__all__
    assert "FakeUserRepository" in fake.__all__
    assert "InMemoryFakeUserRepository" in fake.__all__
    assert "JsonFakeUserRepository" in fake.__all__


def test_fake_package_exports_runtime_contract() -> None:
    import govbr_auth.fake as fake

    assert tuple(field.name for field in fields(FakeLoginCredential)) == (
        "cpf",
        "password",
        "name",
    )
    assert tuple(field.name for field in fields(FakeGovBrEndpoints)) == (
        "authorize",
        "token",
        "userinfo",
        "jwks",
        "issuer",
    )
    assert tuple(field.name for field in fields(FakeGovSimulator)) == (
        "settings",
        "provider",
        "credential_authenticator",
        "users",
        "credentials",
        "prefix",
        "endpoints",
        "http_application",
    )
    assert fake.FakeLoginCredential is FakeLoginCredential
    assert fake.FakeGovBrEndpoints is FakeGovBrEndpoints
    assert fake.FakeGovSimulator is FakeGovSimulator
    assert fake.create_fake_gov_simulator is create_fake_gov_simulator


def test_fake_package_exports_simulator_contract_without_runtime_aliases() -> None:
    import govbr_auth.fake as fake
    import govbr_auth.fake.runtime as runtime_module

    assert hasattr(runtime_module, "FakeGovSimulator")
    assert hasattr(runtime_module, "create_fake_gov_simulator")
    assert fake.FakeGovSimulator is runtime_module.FakeGovSimulator
    assert fake.create_fake_gov_simulator is runtime_module.create_fake_gov_simulator
    assert "FakeGovSimulator" in fake.__all__
    assert "create_fake_gov_simulator" in fake.__all__
    assert "FakeGovBrRuntime" not in fake.__all__
    assert "create_fake_govbr_runtime" not in fake.__all__
    assert not hasattr(fake, "FakeGovBrRuntime")
    assert not hasattr(fake, "create_fake_govbr_runtime")


def test_neutral_modules_do_not_load_web_frameworks() -> None:
    """Importing neutral runtime and presentation modules must load no adapter."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import govbr_auth.fake.runtime\n"
                "import govbr_auth.runtime\n"
                "import govbr_auth.presentation\n"
                "loaded = sorted(name for name in sys.modules "
                "if name.split('.', 1)[0] in "
                "{'fastapi', 'starlette', 'flask', 'werkzeug', 'django', 'asgiref'})\n"
                "print('\\n'.join(loaded))\n"
                "raise SystemExit(bool(loaded))\n"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
