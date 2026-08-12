"""Immutable data models used by the local Fake Gov.br provider."""

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, SecretStr, field_validator

from govbr_auth.core.models import GovBrUser


class FakeClient(BaseModel):
    """Represent a client registered with the local Fake Gov.br provider."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    client_id: str
    client_secret: SecretStr
    registered_redirect_uris: tuple[AnyHttpUrl, ...]

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        """Reject blank client identifiers."""
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(cls, value: SecretStr) -> SecretStr:
        """Reject blank client secrets without disclosing their content."""
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("registered_redirect_uris", mode="before")
    @classmethod
    def validate_redirect_uri_input(cls, value: object) -> tuple[object, ...]:
        """Reject blank or absent registered redirect URIs."""
        if not value:
            raise ValueError("must not be empty")
        try:
            redirect_uris = tuple(value)
        except TypeError as error:
            raise ValueError("registered redirect URIs must be iterable") from error
        if not redirect_uris:
            raise ValueError("must not be empty")
        if any(isinstance(uri, str) and not uri.strip() for uri in redirect_uris):
            raise ValueError("must not be empty")
        return redirect_uris


class FakeUser(GovBrUser):
    """Represent a stable local user with the standard Gov.br user claims."""
