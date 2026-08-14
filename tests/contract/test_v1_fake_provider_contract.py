"""Freeze the public v1 contract of the framework-independent fake provider."""

from dataclasses import fields

from govbr_auth.fake import (
    FakeAuthorizationRedirect,
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeCredentialAuthenticator,
    FakeGovBrProvider,
    FakeOAuthError,
    InMemoryFakeUserRepository,
    FakeTokenRequest,
    FakeTokenResponse,
)


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
    assert fake.InMemoryFakeUserRepository is InMemoryFakeUserRepository
    assert "FakeCredentialAuthenticator" in fake.__all__
    assert "InMemoryFakeUserRepository" in fake.__all__
