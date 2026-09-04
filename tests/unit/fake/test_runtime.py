"""Tests for canonical framework-independent Fake Gov.br composition."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from fastapi.responses import Response
from pydantic import SecretStr, ValidationError

from govbr_auth.fake import FakeUser, InMemoryFakeUserRepository
from govbr_auth.fake import runtime as runtime_module
from govbr_auth.fake.credentials import FakeLoginCredential
from govbr_auth.fastapi import GovBrAuth
from govbr_auth.fake.runtime import create_fake_gov_simulator
from govbr_auth.runtime import (
    GovBrProvider,
    GovBrRuntimeSettings,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    """Return a stable aware time for fake-provider collaborators."""
    return NOW


def test_fake_simulator_exposes_one_http_application_facade(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """The simulator must own the neutral HTTP facade shared by adapters."""
    from govbr_auth.fake.http.application import FakeGovHttpApplication

    factory = getattr(runtime_module, "create_fake_gov_simulator", None)
    assert factory is not None

    simulator = factory(
        fake_settings,
        prefix=fake_settings.fake_provider_prefix,
        clock=fixed_clock,
    )

    assert simulator.provider is not None
    assert simulator.credential_authenticator is not None
    assert simulator.endpoints.authorize.endswith("/authorize")
    assert isinstance(simulator.http_application, FakeGovHttpApplication)


@pytest.fixture
def fake_settings() -> GovBrRuntimeSettings:
    """Provide a complete embedded fake-provider configuration."""
    return GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
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
    runtime = create_fake_gov_simulator(
        fake_settings,
        prefix=fake_settings.fake_provider_prefix,
        clock=fixed_clock,
    )

    assert str(runtime.settings.issuer) == runtime.endpoints.issuer
    assert (
        runtime.credential_authenticator.authenticate(
            cpf="12345678901",
            password=SecretStr("ana-demo"),
        )
        == runtime.users[0]
    )


def test_provider_only_simulator_uses_explicit_empty_prefix(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """A standalone provider must make its root topology explicit."""
    simulator = create_fake_gov_simulator(
        fake_settings,
        prefix="",
        clock=fixed_clock,
    )

    assert simulator.prefix == ""
    assert simulator.endpoints.authorize == "http://127.0.0.1:8000/authorize"


def test_default_credentials_are_derived_from_the_default_user_source(
    fake_settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding one default identity must also add its presented login credential."""
    extra_user = FakeUser(
        sub="11122233344",
        name="Carla Demo",
        email="carla@example.test",
    )
    monkeypatch.setattr(
        runtime_module,
        "_DEFAULT_USERS",
        runtime_module._DEFAULT_USERS + ((extra_user, SecretStr("carla-demo")),),
    )

    runtime = create_fake_gov_simulator(
        fake_settings,
        prefix=fake_settings.fake_provider_prefix,
        clock=fixed_clock,
    )

    assert runtime.credentials[-1] == FakeLoginCredential(
        cpf="11122233344",
        password="carla-demo",
        name="Carla Demo",
    )


def test_fake_login_credential_repr_hides_cpf_and_password() -> None:
    """Credential diagnostics must not disclose login secrets or identifiers."""
    credential = FakeLoginCredential(
        cpf="12345678901",
        password="ana-demo",
        name="Ana Demo",
    )

    rendered = repr(credential)

    assert "12345678901" not in rendered
    assert "ana-demo" not in rendered


def test_fake_runtime_repr_hides_users_and_credentials(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Runtime diagnostics must not include fake identities or credentials."""
    runtime = create_fake_gov_simulator(
        fake_settings,
        prefix=fake_settings.fake_provider_prefix,
        clock=fixed_clock,
    )

    rendered = repr(runtime)

    assert "12345678901" not in rendered
    assert "ana-demo" not in rendered
    assert "ana@example.test" not in rendered


def test_fake_runtime_repr_hides_credential_authenticator(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Runtime diagnostics must not invoke a repository repr that may contain secrets."""

    class SensitiveRepository(InMemoryFakeUserRepository):
        def __repr__(self) -> str:
            return "SensitiveRepository(password=repository-secret-marker)"

    repository = SensitiveRepository(())
    runtime = create_fake_gov_simulator(
        fake_settings,
        prefix=fake_settings.fake_provider_prefix,
        clock=fixed_clock,
        user_repository=repository,
    )

    assert "repository-secret-marker" not in repr(runtime)


def test_explicit_repository_precedes_users_file(
    fake_settings: GovBrRuntimeSettings,
    repository: InMemoryFakeUserRepository,
) -> None:
    """An explicit repository must prevent access to a configured JSON source."""
    runtime = create_fake_gov_simulator(
        fake_settings.model_copy(update={"fake_users_file": Path("missing.json")}),
        prefix=fake_settings.fake_provider_prefix,
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

    runtime = create_fake_gov_simulator(
        fake_settings.model_copy(update={"fake_users_file": users_file}),
        prefix=fake_settings.fake_provider_prefix,
        clock=fixed_clock,
    )

    assert tuple(user.sub for user in runtime.users) == ("44455566677",)
    assert runtime.credentials == ()


@pytest.mark.parametrize(
    ("prefix", "expected_issuer"),
    [
        ("", "http://127.0.0.1:8000/"),
        ("/fake-govbr", "http://127.0.0.1:8000/fake-govbr/"),
    ],
    ids=("provider-only", "end-to-end"),
)
def test_fake_runtime_derives_endpoints_from_explicit_prefix(
    fake_settings: GovBrRuntimeSettings,
    prefix: str,
    expected_issuer: str,
) -> None:
    """Provider-only and mounted runtimes must expose their actual route roots."""
    runtime = create_fake_gov_simulator(
        fake_settings,
        prefix=prefix,
        clock=fixed_clock,
    )

    assert runtime.prefix == prefix
    assert runtime.endpoints.issuer == expected_issuer
    assert runtime.endpoints.authorize == f"{expected_issuer}authorize"
    assert runtime.endpoints.token == f"{expected_issuer}token"
    assert runtime.endpoints.userinfo == f"{expected_issuer}userinfo"
    assert runtime.endpoints.jwks == f"{expected_issuer}jwk"


@pytest.mark.parametrize(
    "invalid_prefix",
    ("/", "/fake-govbr/", "https://example.test/fake-govbr"),
    ids=("root", "trailing-slash", "absolute-url"),
)
def test_fake_runtime_rejects_invalid_explicit_prefix(
    fake_settings: GovBrRuntimeSettings,
    invalid_prefix: str,
) -> None:
    """Simulator topology must reject ambiguous explicit mount prefixes."""
    with pytest.raises(ValueError, match="prefix"):
        create_fake_gov_simulator(
            fake_settings,
            prefix=invalid_prefix,
            clock=fixed_clock,
        )


def test_end_to_end_builder_revalidates_copied_prefix(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Unchecked model copies must not contaminate mounted provider endpoints."""
    invalid_settings = fake_settings.model_copy(
        update={"fake_provider_prefix": "/fake-govbr/"}
    )

    with pytest.raises(ValidationError, match="fake provider prefix"):
        create_fake_gov_simulator(
            invalid_settings,
            prefix=fake_settings.fake_provider_prefix,
            clock=fixed_clock,
        )


@pytest.mark.asyncio
async def test_fake_facade_routes_and_transport_share_one_http_application(
    fake_settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mounted fake routes and transport must reuse one neutral HTTP application."""
    application_calls: list[tuple[object, object]] = []
    sentinel_application = object()

    def build_application(runtime: object, *, clock: object) -> object:
        application_calls.append((runtime, clock))
        return sentinel_application

    monkeypatch.setattr(
        runtime_module,
        "FakeGovHttpApplication",
        build_application,
        raising=False,
    )

    async def success_handler(context: object) -> Response:
        del context
        return Response(status_code=204)

    auth = GovBrAuth(
        settings=fake_settings,
        on_success=success_handler,
    )

    try:
        assert len(application_calls) == 1
        assert application_calls[0][0] is auth.runtime.fake
        assert auth.runtime.fake is not None
        assert auth.runtime.fake.http_application is sentinel_application
    finally:
        await auth.runtime.aclose()
