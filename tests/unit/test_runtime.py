"""Tests for framework-neutral runtime configuration and lifecycle."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.responses import Response
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

import govbr_auth.runtime as runtime_module
from govbr_auth.authentication import AuthenticationService
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import EncryptedTransactionCodec
from govbr_auth.fastapi import create_govbr_router
from govbr_auth.runtime import (
    GovBrClient,
    GovBrProvider,
    GovBrRuntimeSettings,
    create_govbr_runtime,
    utc_now,
)

ROOT_DIR = Path(__file__).parent.parent.parent.resolve()


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runtime configuration tests independent from dotenv-loading tests."""
    for variable in (
        "GOVBR_PROVIDER",
        "GOVBR_ENVIRONMENT",
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_CLIENT_ID",
        "GOVBR_CLIENT_SECRET",
        "GOVBR_REDIRECT_URI",
        "GOVBR_SCOPE",
        "GOVBR_TRANSACTION_SECRET",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
        "GOVBR_CONNECT_TIMEOUT_SECONDS",
        "GOVBR_READ_TIMEOUT_SECONDS",
        "GOVBR_CLOCK_SKEW_SECONDS",
        "GOVBR_FAKE_HOST",
        "GOVBR_FAKE_PORT",
        "GOVBR_FAKE_PROVIDER_PREFIX",
        "GOVBR_FAKE_CLIENT_ID",
        "GOVBR_FAKE_CLIENT_SECRET",
        "GOVBR_FAKE_REDIRECT_URI",
        "GOVBR_FAKE_REQUEST_TTL_SECONDS",
        "GOVBR_FAKE_AUTHORIZATION_CODE_TTL_SECONDS",
        "GOVBR_FAKE_ACCESS_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_ID_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_USERS_FILE",
    ):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def settings() -> GovBrRuntimeSettings:
    """Provide complete official settings for runtime composition."""
    return GovBrRuntimeSettings(
        oauth=GovBrSettings(
            authorization_url="https://sso.example.test/authorize",
            token_url="https://sso.example.test/token",
            userinfo_url="https://sso.example.test/userinfo",
            client_id="test-client",
            client_secret=SecretStr("test-client-secret"),
            redirect_uri="https://consumer.example.test/oauth/callback",
            transaction_secret=SecretStr(Fernet.generate_key().decode("ascii")),
            issuer="https://sso.example.test",
            jwks_url="https://sso.example.test/jwks",
        )
    )


@pytest.fixture
def fake_settings() -> GovBrRuntimeSettings:
    """Provide complete settings for an embedded fake provider."""
    return GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_redirect_uri="http://127.0.0.1:8000/auth/govbr/callback",
    )


def test_runtime_settings_default_to_official(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime must not enable the fake provider implicitly."""
    monkeypatch.delenv("GOVBR_PROVIDER", raising=False)

    settings = GovBrRuntimeSettings.from_environment()

    assert settings.provider is GovBrProvider.OFFICIAL


def test_runtime_settings_select_fake_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit fake provider selection must reach the runtime boundary."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fake")

    settings = GovBrRuntimeSettings.from_environment()

    assert settings.provider is GovBrProvider.FAKE


def test_runtime_settings_build_official_oauth_from_environment() -> None:
    """Official environment fields must populate the nested OAuth settings."""
    transaction_secret = Fernet.generate_key().decode("ascii")
    settings = GovBrRuntimeSettings.from_environment(
        {
            "GOVBR_PROVIDER": "official",
            "GOVBR_ENVIRONMENT": "staging",
            "GOVBR_AUTHORIZATION_URL": "https://sso.example.test/authorize",
            "GOVBR_TOKEN_URL": "https://sso.example.test/token",
            "GOVBR_USERINFO_URL": "https://sso.example.test/userinfo",
            "GOVBR_CLIENT_ID": "test-client",
            "GOVBR_CLIENT_SECRET": "test-client-secret",
            "GOVBR_REDIRECT_URI": "https://consumer.example.test/oauth/callback",
            "GOVBR_SCOPE": "openid profile custom",
            "GOVBR_TRANSACTION_SECRET": transaction_secret,
            "GOVBR_ISSUER": "https://sso.example.test",
            "GOVBR_JWKS_URL": "https://sso.example.test/jwks",
            "GOVBR_CONNECT_TIMEOUT_SECONDS": "7.5",
            "GOVBR_READ_TIMEOUT_SECONDS": "12.5",
            "GOVBR_CLOCK_SKEW_SECONDS": "45",
        }
    )

    assert settings.oauth is not None
    assert settings.provider is GovBrProvider.OFFICIAL
    assert settings.oauth.environment.value == "staging"
    assert str(settings.oauth.authorization_url) == (
        "https://sso.example.test/authorize"
    )
    assert str(settings.oauth.token_url) == "https://sso.example.test/token"
    assert str(settings.oauth.userinfo_url) == "https://sso.example.test/userinfo"
    assert settings.oauth.client_id == "test-client"
    assert settings.oauth.client_secret.get_secret_value() == "test-client-secret"
    assert str(settings.oauth.redirect_uri) == (
        "https://consumer.example.test/oauth/callback"
    )
    assert settings.oauth.scope == "openid profile custom"
    assert settings.oauth.transaction_secret.get_secret_value() == transaction_secret
    assert str(settings.oauth.issuer) == "https://sso.example.test/"
    assert str(settings.oauth.jwks_url) == "https://sso.example.test/jwks"
    assert settings.oauth.connect_timeout_seconds == 7.5
    assert settings.oauth.read_timeout_seconds == 12.5
    assert settings.oauth.clock_skew_seconds == 45


def test_runtime_settings_reject_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported providers must fail before runtime construction."""
    monkeypatch.setenv("GOVBR_PROVIDER", "fallback")

    with pytest.raises(ValueError) as exc_info:
        GovBrRuntimeSettings.from_environment()

    assert type(exc_info.value) is ValueError
    assert str(exc_info.value) == (
        "Configuração Gov.br inválida: valor inválido para GOVBR_PROVIDER."
    )


def test_runtime_settings_reports_environment_mismatch_in_portuguese() -> None:
    """The startup boundary must not expose Pydantic or configured values."""
    sensitive_secret = "sensitive-secret-marker"
    environment = {
        "GOVBR_PROVIDER": "official",
        "GOVBR_ENVIRONMENT": "staging",
        "GOVBR_AUTHORIZATION_URL": "https://sso.staging.acesso.gov.br/authorize",
        "GOVBR_TOKEN_URL": "https://sso.staging.acesso.gov.br/token",
        "GOVBR_USERINFO_URL": "https://sso.staging.acesso.gov.br/userinfo/",
        "GOVBR_CLIENT_ID": "test-client",
        "GOVBR_CLIENT_SECRET": sensitive_secret,
        "GOVBR_REDIRECT_URI": "https://consumer.example.test/oauth/callback",
        "GOVBR_TRANSACTION_SECRET": sensitive_secret,
        "GOVBR_ISSUER": "https://sso.acesso.gov.br/",
        "GOVBR_JWKS_URL": "https://sso.acesso.gov.br/jwk",
    }

    with pytest.raises(ValueError) as exc_info:
        GovBrRuntimeSettings.from_environment(environment)

    assert type(exc_info.value) is ValueError
    assert str(exc_info.value) == (
        "Configuração Gov.br inválida: Endpoints oficiais do Gov.br "
        "incompatíveis com GOVBR_ENVIRONMENT='staging': "
        "GOVBR_ISSUER, GOVBR_JWKS_URL."
    )
    assert sensitive_secret not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_runtime_settings_explains_http_dns_redirect_in_portuguese() -> None:
    """A DNS callback without TLS must identify the variable and correction."""
    environment = {
        "GOVBR_PROVIDER": "official",
        "GOVBR_ENVIRONMENT": "staging",
        "GOVBR_AUTHORIZATION_URL": "https://sso.staging.acesso.gov.br/authorize",
        "GOVBR_TOKEN_URL": "https://sso.staging.acesso.gov.br/token",
        "GOVBR_USERINFO_URL": "https://sso.staging.acesso.gov.br/userinfo/",
        "GOVBR_CLIENT_ID": "test-client",
        "GOVBR_CLIENT_SECRET": "test-client-secret",
        "GOVBR_REDIRECT_URI": "http://app.example.test/oauth/callback",
        "GOVBR_TRANSACTION_SECRET": "test-transaction-secret",
        "GOVBR_ISSUER": "https://sso.staging.acesso.gov.br/",
        "GOVBR_JWKS_URL": "https://sso.staging.acesso.gov.br/jwk",
    }

    with pytest.raises(ValueError) as exc_info:
        GovBrRuntimeSettings.from_environment(environment)

    assert str(exc_info.value) == (
        "Configuração Gov.br inválida: GOVBR_REDIRECT_URI usa HTTP em um host "
        "não-loopback. Configure HTTPS para esse DNS ou use uma URI de loopback."
    )


def test_runtime_settings_reject_unknown_govbr_variable() -> None:
    """A misspelled GOVBR variable must not disappear behind a default."""
    with pytest.raises(
        ValueError,
        match="Configuração.*variável não suportada: GOVBR_FAKE_PORRT",
    ) as captured:
        GovBrRuntimeSettings.from_environment(
            {
                "GOVBR_PROVIDER": "fake",
                "GOVBR_FAKE_PORRT": "sensitive-unknown-value",
            }
        )
    assert "sensitive-unknown-value" not in str(captured.value)


@pytest.mark.parametrize(
    ("environment", "inactive_variable"),
    (
        (
            {"GOVBR_PROVIDER": "official", "GOVBR_FAKE_PORT": "8123"},
            "GOVBR_FAKE_PORT",
        ),
        (
            {
                "GOVBR_PROVIDER": "fake",
                "GOVBR_CONNECT_TIMEOUT_SECONDS": "7",
            },
            "GOVBR_CONNECT_TIMEOUT_SECONDS",
        ),
    ),
    ids=(
        "fake-variable-with-official-provider",
        "official-variable-with-fake-provider",
    ),
)
def test_runtime_settings_warn_about_provider_inactive_variables(
    environment: dict[str, str],
    inactive_variable: str,
) -> None:
    """Removing the warning must make a recognized inactive input silent."""
    with pytest.warns(UserWarning, match=inactive_variable) as captured:
        GovBrRuntimeSettings.from_environment(environment)
    assert environment[inactive_variable] not in str(captured[0].message)
    assert Path(captured[0].filename).name == "test_runtime.py"


@pytest.mark.parametrize(
    "variable",
    (
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
    ),
    ids=("authorize", "token", "userinfo", "redirect", "issuer", "jwks"),
)
def test_fake_environment_rejects_official_endpoint_variables(variable: str) -> None:
    """Fake selection must not silently ignore an official provider endpoint."""
    with pytest.raises(ValueError, match="official endpoint"):
        GovBrRuntimeSettings.from_environment(
            {
                "GOVBR_PROVIDER": "fake",
                variable: "https://sso.example.test/endpoint",
            }
        )


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "example.test"])
def test_runtime_settings_reject_non_loopback_fake_host(host: str) -> None:
    """The local fake provider must not bind a remotely reachable host."""
    with pytest.raises(ValueError, match="Configuração.*GOVBR_FAKE_HOST"):
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_HOST": host}
        )


@pytest.mark.parametrize("port", ["0", "65536"])
def test_runtime_settings_reject_invalid_fake_port(port: str) -> None:
    """The runtime must reject ports outside the TCP port range."""
    with pytest.raises(ValueError, match="Configuração.*GOVBR_FAKE_PORT"):
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_PORT": port}
        )


@pytest.mark.parametrize(
    "prefix",
    (
        "",
        "   ",
        "fake-govbr",
        "/",
        "/fake-govbr/",
        "/fake-govbr?debug=1",
        "/fake-govbr#fragment",
        "https://example.test/fake-govbr",
        "//example.test/fake-govbr",
        "/fake govbr",
        "/fake\\govbr",
        "/fake/./govbr",
        "/fake/../govbr",
        "/fake//govbr",
        "/fake%2Fgovbr",
        "/fake\x00govbr",
    ),
    ids=(
        "empty",
        "whitespace",
        "missing-leading-slash",
        "root",
        "trailing-slash",
        "query",
        "fragment",
        "absolute-url",
        "network-path",
        "embedded-whitespace",
        "backslash",
        "dot-segment",
        "parent-segment",
        "empty-segment",
        "percent-encoding",
        "control-character",
    ),
)
def test_end_to_end_settings_reject_invalid_fake_provider_prefix(
    prefix: str,
) -> None:
    """Mounted fake routes require one unambiguous non-root path prefix."""
    with pytest.raises(ValidationError, match="fake provider prefix"):
        GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_provider_prefix=prefix,
        )


def test_embedded_runtime_revalidates_fake_provider_prefix() -> None:
    """Consumer embedding must validate a prefix unused by provider-only mode."""
    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE).model_copy(
        update={"fake_provider_prefix": "//example.test/fake-govbr"}
    )

    def fail_if_factory_called(_):
        raise AssertionError("invalid prefix must fail before transport composition")

    with pytest.raises(ValueError, match="prefix"):
        create_govbr_runtime(
            settings,
            fake_transport_factory=fail_if_factory_called,
        )


def test_official_runtime_rejects_unvalidated_settings_without_oauth() -> None:
    """Runtime composition must retain its defensive OAuth invariant."""
    settings = GovBrRuntimeSettings.model_construct(
        provider=GovBrProvider.OFFICIAL,
        oauth=None,
    )

    with pytest.raises(ValueError, match="official runtime requires OAuth settings"):
        create_govbr_runtime(settings)


def test_official_runtime_keeps_one_consumer_authentication_stack(
    settings: GovBrRuntimeSettings,
) -> None:
    """Official mode must keep the canonical consumer client and service types."""
    runtime = create_govbr_runtime(settings)

    async def success_handler(context: object) -> Response:
        del context
        return Response(status_code=204)

    router = create_govbr_router(client=runtime.client, on_success=success_handler)
    services = _route_authentication_services(router)

    assert type(runtime.client) is GovBrClient
    assert type(runtime.client._transactions) is EncryptedTransactionCodec
    assert type(runtime.client._validator) is IdTokenValidator
    assert len(services) == 1
    assert type(services[0]) is AuthenticationService
    assert services[0]._client is runtime.client


@pytest.mark.asyncio
async def test_official_runtime_owns_and_closes_created_http_client(
    settings: GovBrRuntimeSettings,
) -> None:
    """A runtime-created HTTP client must be closed with its runtime."""
    runtime = create_govbr_runtime(settings)

    assert runtime.provider is GovBrProvider.OFFICIAL
    assert runtime.fake is None

    await runtime.aclose()

    assert runtime.is_closed is True


@pytest.mark.asyncio
async def test_runtime_does_not_close_injected_http_client(
    settings: GovBrRuntimeSettings,
) -> None:
    """A caller-owned HTTP client must remain usable after runtime closure."""
    async with httpx.AsyncClient() as http:
        runtime = create_govbr_runtime(settings, http=http)

        await runtime.aclose()

        assert http.is_closed is False


@pytest.mark.asyncio
async def test_runtime_context_closes_owned_resources(
    settings: GovBrRuntimeSettings,
) -> None:
    """Leaving a runtime context must complete its owned-resource lifecycle."""
    async with create_govbr_runtime(settings) as runtime:
        assert runtime.is_closed is False

    assert runtime.is_closed is True


@pytest.mark.asyncio
async def test_runtime_closes_an_owned_http_client_only_once(
    settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated closure must not close a runtime-owned client more than once."""

    class CountingAsyncClient(httpx.AsyncClient):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1
            await super().aclose()

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", CountingAsyncClient)
    runtime = create_govbr_runtime(settings)
    owned_http = runtime.client._http

    await runtime.aclose()
    await runtime.aclose()

    assert isinstance(owned_http, CountingAsyncClient)
    assert owned_http.close_calls == 1


def test_official_runtime_validates_dependencies_before_creating_owned_http(
    settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid transaction encryption must not allocate a client to leak."""
    assert settings.oauth is not None
    invalid_settings = settings.model_copy(
        update={
            "oauth": settings.oauth.model_copy(
                update={"transaction_secret": SecretStr("invalid-fernet-key")}
            )
        }
    )
    http_created = False

    def fail_if_http_created() -> httpx.AsyncClient:
        nonlocal http_created
        http_created = True
        raise AssertionError("the owned HTTP client must not be created")

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fail_if_http_created)

    with pytest.raises(ValueError):
        create_govbr_runtime(invalid_settings)

    assert http_created is False


def test_fake_runtime_uses_its_exact_endpoint_set(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Consumer settings must be derived from the composed fake provider."""
    supplied_fake = None

    def transport_factory(fake):
        nonlocal supplied_fake
        supplied_fake = fake
        return httpx.MockTransport(lambda _: httpx.Response(500))

    runtime = create_govbr_runtime(
        fake_settings,
        fake_transport_factory=transport_factory,
        clock=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert runtime.fake is supplied_fake
    assert runtime.fake is not None
    assert (
        str(runtime.client._settings.authorization_url)
        == runtime.fake.endpoints.authorize
    )
    assert str(runtime.client._settings.token_url) == runtime.fake.endpoints.token
    assert str(runtime.client._settings.userinfo_url) == runtime.fake.endpoints.userinfo
    assert str(runtime.client._settings.jwks_url) == runtime.fake.endpoints.jwks
    assert str(runtime.client._settings.issuer) == runtime.fake.endpoints.issuer


def test_fake_consumer_uses_distinct_provider_and_transaction_secrets(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Compromising one fake-flow codec must not compromise the other."""
    runtime = create_govbr_runtime(
        fake_settings,
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda __: httpx.Response(500)
        ),
    )

    assert runtime.fake is not None
    assert (
        runtime.client._settings.transaction_secret
        != runtime.fake.settings.artifact_secret
    )


def test_fake_consumer_runtime_mounts_provider_below_configured_prefix(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Embedded consumers must not collide with application root routes."""
    runtime = create_govbr_runtime(
        fake_settings,
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda __: httpx.Response(500)
        ),
    )

    assert runtime.fake is not None
    assert runtime.fake.prefix == fake_settings.fake_provider_prefix
    assert runtime.fake.endpoints.authorize.endswith("/fake-govbr/authorize")


@pytest.mark.asyncio
async def test_embedded_fake_runtime_always_uses_configured_provider_prefix(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Embedded runtimes must never expose provider endpoints at the root."""
    runtime = create_govbr_runtime(
        fake_settings,
        fake_transport_factory=lambda fake: httpx.MockTransport(
            lambda request: httpx.Response(500)
        ),
    )

    try:
        assert runtime.fake is not None
        assert runtime.fake.prefix == fake_settings.fake_provider_prefix
        assert runtime.fake.endpoints.authorize.endswith("/fake-govbr/authorize")
    finally:
        await runtime.aclose()


def test_fake_runtime_requires_transport_factory_before_allocating_http(
    fake_settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ASGI composition must fail without leaking an HTTP client."""
    http_created = False

    def fail_if_http_created(*args: object, **kwargs: object) -> httpx.AsyncClient:
        nonlocal http_created
        http_created = True
        raise AssertionError("the owned HTTP client must not be created")

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fail_if_http_created)

    with pytest.raises(ValueError, match="fake transport factory"):
        create_govbr_runtime(fake_settings)

    assert http_created is False


@pytest.mark.asyncio
async def test_fake_runtime_rejects_injected_http_instead_of_transport_factory(
    fake_settings: GovBrRuntimeSettings,
) -> None:
    """Fake composition must let the adapter receive the composed provider."""
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError, match="does not accept an HTTP client"):
            create_govbr_runtime(
                fake_settings,
                http=http,
                fake_transport_factory=lambda _: httpx.MockTransport(
                    lambda __: httpx.Response(500)
                ),
            )


def test_fake_runtime_validates_transport_before_allocating_http(
    fake_settings: GovBrRuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid adapter result must fail before an HTTP client is owned."""
    http_created = False

    def fail_if_http_created(*args: object, **kwargs: object) -> httpx.AsyncClient:
        nonlocal http_created
        http_created = True
        raise AssertionError("the owned HTTP client must not be created")

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fail_if_http_created)

    with pytest.raises(TypeError, match="AsyncBaseTransport"):
        create_govbr_runtime(
            fake_settings,
            fake_transport_factory=lambda _: object(),
        )

    assert http_created is False


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    """Runtime clocks must supply an aware datetime in the UTC timezone."""
    current_time = utc_now()

    assert current_time.tzinfo is UTC
    assert current_time.utcoffset().total_seconds() == 0


def test_runtime_source_has_no_web_framework_imports() -> None:
    """Runtime composition must remain usable without a web framework."""
    source = ROOT_DIR.joinpath("govbr_auth/runtime.py").read_text(encoding="utf-8")

    assert all(
        name not in source for name in ("fastapi", "starlette", "flask", "django")
    )


def _route_authentication_services(router: object) -> list[AuthenticationService]:
    services: list[AuthenticationService] = []
    seen: set[int] = set()
    for route in getattr(router, "routes", ()):
        closure = getattr(route.endpoint, "__closure__", None) or ()
        for cell in closure:
            value = cell.cell_contents
            if type(value) is AuthenticationService and id(value) not in seen:
                seen.add(id(value))
                services.append(value)
    return services
