"""Check that malformed configuration is rejected before resource allocation."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import AnyHttpUrl, SecretStr, ValidationError

from govbr_auth.adapters import _runtime as adapter_runtime
from govbr_auth.core.authorization import AuthorizationBuilder
from govbr_auth.core.transactions import EncryptedTransactionCodec
from govbr_auth.fake.credentials import InMemoryFakeUserRepository
from govbr_auth.fake.models import FakeClient, FakeUser
from govbr_auth.fake.runtime import create_fake_gov_simulator
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings, _fake_oauth_settings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


@pytest.fixture
def fake_settings():
    return GovBrRuntimeSettings(provider=GovBrProvider.FAKE)


@pytest.mark.parametrize("prefix", ("relative", "/double//segment", "/trailing/"))
def test_shared_adapter_preparation_rejects_noncanonical_prefix(fake_settings, prefix):
    with pytest.raises(ValueError, match="canonical path"):
        adapter_runtime.prepare_adapter_runtime_settings(fake_settings, prefix=prefix)


def test_callback_route_rejects_invalid_utf8_path(fake_settings):
    oauth = fake_settings.oauth.model_copy(
        update={"redirect_uri": AnyHttpUrl("http://localhost/callback%FF")}
    )
    settings = fake_settings.model_copy(update={"oauth": oauth})
    with pytest.raises(ValueError, match="not route-safe") as caught:
        adapter_runtime.prepare_adapter_runtime_settings(settings, prefix="/auth/govbr")
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


def test_fake_callback_preparation_rejects_incomplete_settings(fake_settings):
    incomplete = fake_settings.model_copy(update={"oauth": None})
    with pytest.raises(ValueError, match="requires OAuth settings"):
        adapter_runtime.prepare_adapter_runtime_settings(
            incomplete, prefix="/auth/govbr"
        )


def test_borrowed_fake_runtime_rejects_missing_oauth_settings(fake_settings):
    simulator = create_fake_gov_simulator(
        fake_settings, prefix="/fake-govbr", clock=lambda: NOW
    )
    incomplete = fake_settings.model_copy(update={"oauth": None})
    runtime = SimpleNamespace(settings=incomplete, fake=simulator)
    with pytest.raises(ValueError, match="requires OAuth settings"):
        adapter_runtime.create_adapter_runtime(
            settings=None,
            runtime=runtime,
            prefix="/auth/govbr",
            clock=lambda: NOW,
            user_repository=None,
            fake_transport_factory=lambda fake: pytest.fail("must not allocate"),
        )


def test_borrowed_fake_runtime_rejects_mismatched_callback(fake_settings):
    simulator = create_fake_gov_simulator(
        fake_settings, prefix="/fake-govbr", clock=lambda: NOW
    )
    oauth = fake_settings.oauth.model_copy(
        update={"redirect_uri": AnyHttpUrl("http://localhost/different-callback")}
    )
    runtime = SimpleNamespace(
        settings=fake_settings.model_copy(update={"oauth": oauth}),
        fake=simulator,
    )
    with pytest.raises(ValueError, match="does not match"):
        adapter_runtime.create_adapter_runtime(
            settings=None,
            runtime=runtime,
            prefix="/auth/govbr",
            clock=lambda: NOW,
            user_repository=None,
            fake_transport_factory=lambda fake: pytest.fail("must not allocate"),
        )


def test_logout_builder_rejects_absent_logout_configuration(fake_settings):
    oauth = fake_settings.oauth.model_copy(
        update={"logout_url": None, "post_logout_redirect_uri": None}
    )
    codec = EncryptedTransactionCodec(oauth.transaction_secret)
    builder = AuthorizationBuilder(oauth, codec)
    with pytest.raises(ValueError, match="must be configured together"):
        builder.build_logout()


def test_fake_simulator_rejects_noncanonical_prefix(fake_settings):
    with pytest.raises(ValueError, match="canonical path"):
        create_fake_gov_simulator(
            fake_settings, prefix="/bad//prefix", clock=lambda: NOW
        )


def test_fake_simulator_fails_closed_if_revalidation_returns_incomplete_settings(
    fake_settings, monkeypatch
):
    """Retain the defensive check if the settings collaborator violates its contract."""
    incomplete = fake_settings.model_copy(update={"oauth": None})
    monkeypatch.setattr(
        GovBrRuntimeSettings,
        "model_validate",
        classmethod(lambda cls, values: incomplete),
    )
    with pytest.raises(ValueError, match="requires OAuth settings"):
        create_fake_gov_simulator(fake_settings, prefix="/fake", clock=lambda: NOW)


def test_consumer_endpoint_composition_rejects_incomplete_oauth(fake_settings):
    incomplete = fake_settings.model_copy(update={"oauth": None})
    with pytest.raises(ValueError, match="requires OAuth settings"):
        _fake_oauth_settings(incomplete, None)


@pytest.mark.parametrize(
    "cpf", ("", "not-a-cpf", "１２３４５６７８９０１", "123456789012")
)
def test_invalid_cpf_cannot_resolve_or_authenticate_a_user(cpf):
    user = FakeUser(sub="11122233344", name="Test User")
    repository = InMemoryFakeUserRepository(((user, SecretStr("test-password")),))
    assert repository.get(cpf) is None
    assert repository.authenticate(cpf=cpf, password=SecretStr("test-password")) is None
    assert repository.get("111.222.333-44") == user


@pytest.mark.parametrize("invalid", (None, [], 123, [" "], ["http://localhost/", ""]))
def test_fake_client_rejects_invalid_registered_redirects(invalid):
    with pytest.raises(ValidationError):
        FakeClient(
            client_id="test-client",
            client_secret=SecretStr("test-secret"),
            registered_redirect_uris=invalid,
        )


def test_fake_client_rejects_exhausted_redirect_iterator():
    with pytest.raises(ValidationError, match="must not be empty"):
        FakeClient(
            client_id="test-client",
            client_secret=SecretStr("test-secret"),
            registered_redirect_uris=iter(()),
        )


def test_environment_reports_missing_fields_without_echoing_values():
    with pytest.raises(ValueError, match="variável obrigatória ausente") as caught:
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "official", "GOVBR_CLIENT_ID": "private-client-marker"}
        )
    assert "GOVBR_CLIENT_SECRET" in str(caught.value)
    assert "private-client-marker" not in str(caught.value)


def test_environment_reports_invalid_cross_field_configuration():
    with pytest.raises(ValueError, match="combinação de valores inválida"):
        GovBrRuntimeSettings.from_environment(
            {"GOVBR_PROVIDER": "fake", "GOVBR_FAKE_PROVIDER_PREFIX": "/bad//prefix"}
        )
