"""Tests for strict local Fake Gov.br configuration."""

import pytest
from pydantic import ValidationError

from govbr_auth.fake import FakeClient, FakeGovBrSettings, FakeUser


@pytest.fixture
def valid_client_data() -> dict[str, object]:
    return {
        "client_id": "example-client",
        "client_secret": "example-client-secret",
        "registered_redirect_uris": ("https://consumer.example.test/oauth/callback",),
    }


@pytest.fixture
def valid_settings_data(valid_client_data: dict[str, object]) -> dict[str, object]:
    return {
        "base_url": "http://127.0.0.1:8000",
        "issuer": "http://127.0.0.1:8000",
        "artifact_secret": "local-artifact-secret",
        "request_ttl_seconds": 300,
        "authorization_code_ttl_seconds": 60,
        "access_token_ttl_seconds": 600,
        "id_token_ttl_seconds": 600,
        "clients": (valid_client_data,),
    }


def test_fake_settings_reject_non_loopback_by_default(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["base_url"] = "https://fake.example.gov.br"

    with pytest.raises(ValidationError, match="fake provider must use a loopback host"):
        FakeGovBrSettings(**valid_settings_data)


def test_fake_settings_rejects_remote_issuer_with_loopback_base_url(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["issuer"] = "https://remote.example.test"

    with pytest.raises(ValidationError, match="fake provider must use a loopback host"):
        FakeGovBrSettings(**valid_settings_data)


@pytest.mark.parametrize(
    "base_url",
    [
        pytest.param("http://localhost:8000", id="localhost"),
        pytest.param("http://127.0.0.1:8000", id="ipv4_loopback"),
        pytest.param("http://[::1]:8000", id="ipv6_loopback"),
    ],
)
def test_fake_settings_accepts_loopback_hosts(
    valid_settings_data: dict[str, object], base_url: str
) -> None:
    valid_settings_data["base_url"] = base_url
    valid_settings_data["issuer"] = base_url

    settings = FakeGovBrSettings(**valid_settings_data)

    assert str(settings.base_url) == f"{base_url}/"


def test_fake_settings_accepts_non_loopback_with_explicit_override(
    valid_settings_data: dict[str, object],
) -> None:
    valid_settings_data["base_url"] = "https://fake.example.gov.br"
    valid_settings_data["issuer"] = "https://fake.example.gov.br"
    valid_settings_data["allow_non_loopback"] = True

    settings = FakeGovBrSettings(**valid_settings_data)

    assert settings.allow_non_loopback is True


def test_fake_settings_forbids_unknown_fields(
    valid_settings_data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        FakeGovBrSettings(**valid_settings_data, unexpected="value")


def test_fake_settings_is_frozen(valid_settings_data: dict[str, object]) -> None:
    settings = FakeGovBrSettings(**valid_settings_data)

    with pytest.raises(ValidationError, match="frozen"):
        settings.request_ttl_seconds = 60


@pytest.mark.parametrize(
    "field_name",
    [
        pytest.param("artifact_secret", id="artifact_secret"),
    ],
)
def test_fake_settings_rejects_blank_security_values(
    valid_settings_data: dict[str, object], field_name: str
) -> None:
    valid_settings_data[field_name] = "   "

    with pytest.raises(ValidationError, match="must not be empty"):
        FakeGovBrSettings(**valid_settings_data)


@pytest.mark.parametrize(
    "field_name",
    [
        pytest.param("request_ttl_seconds", id="request_ttl"),
        pytest.param("authorization_code_ttl_seconds", id="authorization_code_ttl"),
        pytest.param("access_token_ttl_seconds", id="access_token_ttl"),
        pytest.param("id_token_ttl_seconds", id="id_token_ttl"),
    ],
)
def test_fake_settings_rejects_non_positive_ttls(
    valid_settings_data: dict[str, object], field_name: str
) -> None:
    valid_settings_data[field_name] = 0

    with pytest.raises(ValidationError, match="greater than 0"):
        FakeGovBrSettings(**valid_settings_data)


def test_fake_settings_rejects_duplicate_client_ids(
    valid_settings_data: dict[str, object], valid_client_data: dict[str, object]
) -> None:
    valid_settings_data["clients"] = (valid_client_data, valid_client_data.copy())

    with pytest.raises(ValidationError, match="duplicate fake client id"):
        FakeGovBrSettings(**valid_settings_data)


def test_fake_client_uses_immutable_redirect_uris_and_secret(
    valid_client_data: dict[str, object],
) -> None:
    client = FakeClient(**valid_client_data)

    assert tuple(str(uri) for uri in client.registered_redirect_uris) == (
        "https://consumer.example.test/oauth/callback",
    )
    assert client.client_secret.get_secret_value() == "example-client-secret"


def test_fake_client_preserves_redirect_uri_from_one_shot_iterator(
    valid_client_data: dict[str, object],
) -> None:
    valid_client_data["registered_redirect_uris"] = iter(
        ("https://consumer.example.test/oauth/callback",)
    )

    client = FakeClient(**valid_client_data)

    assert tuple(str(uri) for uri in client.registered_redirect_uris) == (
        "https://consumer.example.test/oauth/callback",
    )


def test_fake_client_rejects_truthy_non_iterable_redirect_uris(
    valid_client_data: dict[str, object],
) -> None:
    valid_client_data["registered_redirect_uris"] = 1

    with pytest.raises(
        ValidationError, match="registered redirect URIs must be iterable"
    ):
        FakeClient(**valid_client_data)


def test_fake_client_is_frozen(valid_client_data: dict[str, object]) -> None:
    client = FakeClient(**valid_client_data)

    with pytest.raises(ValidationError, match="frozen"):
        client.client_id = "another-client"


@pytest.mark.parametrize(
    "field_name, value",
    [
        pytest.param("client_id", "   ", id="blank_client_id"),
        pytest.param("client_secret", "   ", id="blank_client_secret"),
        pytest.param("registered_redirect_uris", ("   ",), id="blank_redirect_uri"),
    ],
)
def test_fake_client_rejects_blank_security_values(
    valid_client_data: dict[str, object], field_name: str, value: object
) -> None:
    valid_client_data[field_name] = value

    with pytest.raises(ValidationError, match="must not be empty"):
        FakeClient(**valid_client_data)


def test_fake_user_uses_the_standard_govbr_user_claims() -> None:
    user = FakeUser(
        sub="subject-123",
        name="Maria da Silva",
        email="maria@example.test",
        email_verified=True,
    )

    assert user.model_dump() == {
        "sub": "subject-123",
        "name": "Maria da Silva",
        "social_name": None,
        "given_name": None,
        "family_name": None,
        "middle_name": None,
        "nickname": None,
        "preferred_username": None,
        "profile": None,
        "picture": None,
        "website": None,
        "email": "maria@example.test",
        "email_verified": True,
        "gender": None,
        "birthdate": None,
        "zoneinfo": None,
        "locale": None,
        "phone_number": None,
        "phone_number_verified": None,
        "address": None,
        "updated_at": None,
    }


def test_fake_user_forbids_unknown_claims() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        FakeUser(sub="subject-123", unexpected="claim")
