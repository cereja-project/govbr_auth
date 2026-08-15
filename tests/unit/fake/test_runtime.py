"""Tests for canonical framework-independent Fake Gov.br composition."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from govbr_auth.fake import FakeUser, InMemoryFakeUserRepository
from govbr_auth.fake.runtime import create_fake_govbr_runtime
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    """Return a stable aware time for fake-provider collaborators."""
    return NOW


@pytest.fixture
def fake_settings() -> GovBrRuntimeSettings:
    """Provide a complete embedded fake-provider configuration."""
    return GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_end_to_end=True,
        fake_redirect_uri="http://127.0.0.1:8000/auth/govbr/callback",
    )


@pytest.fixture
def repository() -> InMemoryFakeUserRepository:
    """Provide a caller-owned fake-user repository."""
    return InMemoryFakeUserRepository(
        (
            (
                FakeUser(
                    sub="11122233344",
                    name="Explicit User",
                    email="explicit@example.test",
                ),
                SecretStr("explicit-password"),
            ),
        )
    )


def test_fake_runtime_contains_one_consistent_provider_graph(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Default composition must expose one coherent provider and user graph."""
    runtime = create_fake_govbr_runtime(fake_settings, clock=fixed_clock)

    assert str(runtime.settings.issuer) == runtime.endpoints.issuer
    assert (
        runtime.credential_authenticator.authenticate(
            cpf="12345678901",
            password=SecretStr("ana-demo"),
        )
        == runtime.users[0]
    )


def test_explicit_repository_precedes_users_file(
    fake_settings: GovBrRuntimeSettings,
    repository: InMemoryFakeUserRepository,
) -> None:
    """An explicit repository must prevent access to a configured JSON source."""
    runtime = create_fake_govbr_runtime(
        fake_settings.model_copy(update={"fake_users_file": Path("missing.json")}),
        clock=fixed_clock,
        user_repository=repository,
    )

    assert runtime.credential_authenticator is repository


def test_json_repository_precedes_default_users(
    fake_settings: GovBrRuntimeSettings,
    tmp_path: Path,
) -> None:
    """A configured JSON source must replace the demonstrative defaults."""
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "44455566677",
                        "password": "json-password",
                        "name": "JSON User",
                        "email": "json@example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    runtime = create_fake_govbr_runtime(
        fake_settings.model_copy(update={"fake_users_file": users_file}),
        clock=fixed_clock,
    )

    assert tuple(user.sub for user in runtime.users) == ("44455566677",)
    assert runtime.credentials == ()


@pytest.mark.parametrize(
    ("end_to_end", "expected_prefix", "expected_issuer"),
    [
        (False, "", "http://127.0.0.1:8000/"),
        (True, "/fake-govbr", "http://127.0.0.1:8000/fake-govbr/"),
    ],
    ids=("provider-only", "end-to-end"),
)
def test_fake_runtime_derives_endpoints_from_launch_mode(
    fake_settings: GovBrRuntimeSettings,
    end_to_end: bool,
    expected_prefix: str,
    expected_issuer: str,
) -> None:
    """Provider-only and mounted runtimes must expose their actual route roots."""
    settings = fake_settings.model_copy(update={"fake_end_to_end": end_to_end})

    runtime = create_fake_govbr_runtime(settings, clock=fixed_clock)

    assert runtime.prefix == expected_prefix
    assert runtime.endpoints.issuer == expected_issuer
    assert runtime.endpoints.authorize == f"{expected_issuer}authorize"
    assert runtime.endpoints.token == f"{expected_issuer}token"
    assert runtime.endpoints.userinfo == f"{expected_issuer}userinfo"
    assert runtime.endpoints.jwks == f"{expected_issuer}jwk"
