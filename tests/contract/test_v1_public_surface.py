"""Freeze the framework-neutral v1 public and distribution contracts."""

import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

from cryptography.fernet import Fernet
from packaging.requirements import Requirement

import govbr_auth
from govbr_auth import core, fake

PROJECT_ROOT = Path(__file__).parents[2]


def _project_metadata() -> dict[str, object]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]


def _build_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    } | {"PYTHONUTF8": "1"}


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
        "EncryptedTransactionCodec",
        "InvalidIdTokenError",
        "InvalidStateError",
        "ProviderEnvironment",
        "TokenSet",
        "TransactionCodec",
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
        "FakeGovSimulator",
        "FakeGovBrSettings",
        "FakeLoginCredential",
        "FakeOAuthError",
        "FakeSigningKey",
        "FakeTokenIssuer",
        "FakeTokenRequest",
        "FakeTokenResponse",
        "FakeUser",
        "FakeUserRepository",
        "FakeUserStore",
        "InMemoryAuthorizationCodeReplayStore",
        "InMemoryFakeUserStore",
        "InMemoryFakeUserRepository",
        "JsonFakeUserRepository",
        "create_fake_gov_simulator",
        "create_fake_app",
        "create_fake_govbr_app",
        "create_fake_govbr_router",
        "run",
    )


def test_base_dependencies_are_exactly_framework_neutral() -> None:
    metadata = _project_metadata()

    dependency_names = {
        Requirement(dependency).name.lower() for dependency in metadata["dependencies"]
    }

    assert dependency_names == {
        "cryptography",
        "httpx",
        "pydantic",
        "pyjwt",
        "python-dotenv",
    }
    assert set(metadata["dependencies"]) == {
        "httpx>=0.28.1,<1",
        "PyJWT>=2.13,<3",
        "cryptography>=50.0.0,<51",
        "python-dotenv>=1.2.3,<2",
        "pydantic>=2.13.5,<3",
    }


def test_project_version_is_static_without_importing_runtime_dependencies() -> None:
    metadata = _project_metadata()

    assert metadata["version"] == "1.0.0"
    assert "dynamic" not in metadata


def test_stable_release_metadata_claims_production_maturity() -> None:
    classifiers = _project_metadata()["classifiers"]

    assert "Development Status :: 5 - Production/Stable" in classifiers
    assert "Development Status :: 4 - Beta" not in classifiers


def test_optional_dependencies_expose_framework_and_development_tools() -> None:
    metadata = _project_metadata()

    optional_dependencies = metadata["optional-dependencies"]

    assert set(optional_dependencies) == {"dev", "fake", "fastapi", "django", "flask"}
    assert optional_dependencies["fastapi"] == [
        "fastapi>=0.141.1,<1",
        "python-multipart>=0.0.32,<1",
    ]
    assert optional_dependencies["django"] == [
        "Django>=5.2.17,<7",
        "asgiref>=3.12.1,<4",
    ]
    assert optional_dependencies["flask"] == [
        "Flask>=3.1.3,<4",
        "asgiref>=3.12.1,<4",
    ]
    assert optional_dependencies["fake"] == [
        "fastapi>=0.141.1,<1",
        "python-multipart>=0.0.32,<1",
        "uvicorn>=0.52.4,<1",
    ]
    assert optional_dependencies["dev"] == [
        "uvicorn",
        "pytest",
        "pytest-asyncio",
        "pytest-mock",
        "black",
        "build",
        "setuptools>=84.0.0",
        "wheel",
        "flake8",
        "pytest-cov",
        "PyYAML",
    ]


def test_development_install_enables_every_tested_framework_extra() -> None:
    requirements = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert requirements.splitlines() == [
        "-e .[fake,dev,django,flask]",
        "respx>=0.23.1,<1",
    ]


def test_project_metadata_mentions_supported_frameworks() -> None:
    metadata = _project_metadata()

    description = metadata["description"].lower()
    keywords = tuple(keyword.lower() for keyword in metadata["keywords"])

    assert all(framework in description for framework in ("fastapi", "django", "flask"))
    assert all(framework in keywords for framework in ("fastapi", "django", "flask"))


def test_built_distributions_contain_only_publishable_package_artifacts(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=_build_environment(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (wheel_path,) = tmp_path.glob("*.whl")
    (sdist_path,) = tmp_path.glob("*.tar.gz")

    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_entries = wheel.namelist()
    with tarfile.open(sdist_path, mode="r:gz") as sdist:
        sdist_entries = sdist.getnames()

    invalid_entries = [
        entry
        for entry in wheel_entries + sdist_entries
        if entry.endswith(".pyc") or "__pycache__" in entry.split("/")
    ]
    wheel_roots = {entry.split("/", 1)[0] for entry in wheel_entries}

    assert invalid_entries == []
    assert wheel_roots == {"govbr_auth", "govbr_auth-1.0.0.dist-info"}
