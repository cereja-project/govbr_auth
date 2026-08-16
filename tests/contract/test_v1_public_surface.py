"""Freeze the FastAPI-only v1 public and distribution contracts."""

import importlib.util
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from packaging.requirements import Requirement

import govbr_auth
from govbr_auth import core, fake

PROJECT_ROOT = Path(__file__).parents[2]


def _project_metadata() -> dict[str, object]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]


def test_top_level_exports_exact_framework_neutral_v1_surface() -> None:
    assert tuple(govbr_auth.__all__) == ("generate_transaction_secret",)
    assert not hasattr(govbr_auth, "AuthContext")
    assert not hasattr(govbr_auth, "GovBrAuth")


def test_generate_transaction_secret_returns_valid_unique_fernet_keys() -> None:
    first_secret = govbr_auth.generate_transaction_secret()
    second_secret = govbr_auth.generate_transaction_secret()

    first_fernet = Fernet(first_secret.encode("ascii"))
    encrypted = first_fernet.encrypt(b"transaction-state")

    assert first_fernet.decrypt(encrypted) == b"transaction-state"
    assert len(first_secret) == 44
    assert first_secret != second_secret


def test_core_exports_exact_async_v1_surface() -> None:
    assert tuple(core.__all__) == (
        "AuthenticationResult",
        "AuthTransaction",
        "AuthorizationBuilder",
        "AuthorizationRequest",
        "ExpiredTransactionError",
        "GovBrAddress",
        "GovBrAuthError",
        "GovBrClient",
        "GovBrSettings",
        "GovBrUser",
        "IdTokenValidator",
        "InMemoryTransactionStore",
        "InvalidIdTokenError",
        "InvalidStateError",
        "ProviderEnvironment",
        "TokenSet",
        "TransactionStore",
    )


def test_fake_exports_exact_optional_provider_surface() -> None:
    assert tuple(fake.__all__) == (
        "AccessTokenArtifact",
        "AuthorizationCodeArtifact",
        "AuthorizationCodeReplayStore",
        "AuthorizationRequestArtifact",
        "FakeArtifactCodec",
        "FakeAuthorizationRedirect",
        "FakeAuthorizationRequest",
        "FakeAuthorizationSession",
        "FakeClient",
        "FakeClientCredentials",
        "FakeCredentialAuthenticator",
        "FakeGovBrEndpoints",
        "FakeGovBrProvider",
        "FakeGovBrRuntime",
        "FakeGovBrSettings",
        "FakeLoginCredential",
        "FakeOAuthError",
        "FakeSigningKey",
        "FakeTokenIssuer",
        "FakeTokenRequest",
        "FakeTokenResponse",
        "FakeUser",
        "FakeUserStore",
        "InMemoryAuthorizationCodeReplayStore",
        "InMemoryFakeUserStore",
        "InMemoryFakeUserRepository",
        "JsonFakeUserRepository",
        "create_fake_govbr_runtime",
        "create_fake_govbr_app",
        "create_fake_govbr_router",
    )


@pytest.mark.parametrize(
    "module_name",
    (
        "govbr_auth.controller",
        "govbr_auth.core.config",
        "govbr_auth.core.govbr",
        "govbr_auth.fake_govbr",
        "govbr_auth.utils",
    ),
    ids=("controller", "legacy-config", "sync-core", "legacy-fake", "legacy-utils"),
)
def test_legacy_modules_are_not_importable(module_name: str) -> None:
    assert importlib.util.find_spec(module_name) is None


@pytest.mark.parametrize(
    "symbol_name",
    (
        "AuthorizationRequest",
        "FakeGovBrService",
        "FakeUserData",
        "GovBrAuthorize",
        "GovBrAuthenticationError",
        "GovBrConfig",
        "GovBrConnector",
        "GovBrException",
        "GovBrIntegration",
        "create_default_fake_users",
        "process_fake_login",
        "render_fake_login_page",
    ),
    ids=(
        "legacy-authorization-request",
        "legacy-fake-service",
        "legacy-fake-user",
        "legacy-authorize",
        "legacy-auth-error",
        "legacy-config",
        "legacy-connector",
        "legacy-error",
        "legacy-integration",
        "legacy-default-users",
        "legacy-fake-login",
        "legacy-fake-page",
    ),
)
def test_top_level_has_no_legacy_or_fake_provider_symbol(symbol_name: str) -> None:
    assert not hasattr(govbr_auth, symbol_name)


def test_base_dependencies_are_exactly_fastapi_consumer_dependencies() -> None:
    metadata = _project_metadata()

    dependency_names = {
        Requirement(dependency).name.lower() for dependency in metadata["dependencies"]
    }

    assert dependency_names == {
        "cryptography",
        "fastapi",
        "httpx",
        "pydantic",
        "pyjwt",
        "python-dotenv",
    }


def test_project_version_is_static_without_importing_runtime_dependencies() -> None:
    metadata = _project_metadata()

    assert metadata["version"] == "1.0.0rc1"
    assert "dynamic" not in metadata


def test_optional_dependencies_split_fake_demo_and_development_tools() -> None:
    metadata = _project_metadata()

    optional_dependencies = metadata["optional-dependencies"]

    assert set(optional_dependencies) == {"demo", "dev", "fake"}
    assert optional_dependencies["fake"] == ["python-multipart"]
    assert optional_dependencies["demo"] == ["python-multipart", "uvicorn"]
    assert optional_dependencies["dev"] == [
        "uvicorn",
        "pytest",
        "pytest-asyncio",
        "pytest-mock",
        "black",
        "build",
        "flake8",
        "pytest-cov",
        "PyYAML",
    ]


def test_development_install_enables_fake_and_dev_extras() -> None:
    requirements = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert requirements.splitlines() == ["-e .[fake,dev]", "respx>=0.22,<1"]


def test_project_metadata_mentions_only_fastapi_framework() -> None:
    metadata = _project_metadata()

    description = metadata["description"].lower()
    keywords = tuple(keyword.lower() for keyword in metadata["keywords"])

    assert "fastapi" in description
    assert "flask" not in description
    assert "django" not in description
    assert "fastapi" in keywords
    assert "flask" not in keywords
    assert "django" not in keywords


def test_built_distributions_exclude_legacy_and_cache_artifacts(
    tmp_path: Path,
) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--outdir",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    (wheel_path,) = tmp_path.glob("*.whl")
    (sdist_path,) = tmp_path.glob("*.tar.gz")

    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_entries = wheel.namelist()
    with tarfile.open(sdist_path, mode="r:gz") as sdist:
        sdist_entries = sdist.getnames()

    forbidden_paths = {
        "examples/django_example",
        "examples/example_simple_app.py",
        "govbr_auth/controller.py",
        "govbr_auth/core/config.py",
        "govbr_auth/core/govbr.py",
        "govbr_auth/fake_govbr.py",
        "govbr_auth/utils.py",
    }
    invalid_entries = [
        entry
        for entry in wheel_entries + sdist_entries
        if entry.endswith(".pyc")
        or "__pycache__" in entry.split("/")
        or any(
            entry == forbidden_path or entry.endswith(f"/{forbidden_path}")
            for forbidden_path in forbidden_paths
        )
    ]

    assert invalid_entries == []
