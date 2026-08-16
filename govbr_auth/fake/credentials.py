"""Credential sources for the explicit local Fake Gov.br provider."""

from dataclasses import dataclass, field
from pathlib import Path
from secrets import compare_digest
from typing import Protocol

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

from govbr_auth.fake.models import FakeUser


@dataclass(frozen=True, slots=True)
class FakeLoginCredential:
    """Describe a demonstrative credential without attaching it to a user."""

    cpf: str = field(repr=False)
    password: str = field(repr=False)
    name: str


class FakeCredentialAuthenticator(Protocol):
    """Define a source that authenticates local fake users."""

    def authenticate(self, *, cpf: str, password: SecretStr) -> FakeUser | None:
        """Authenticate a user from CPF and password credentials."""

        ...


def normalize_fake_cpf(value: str) -> str:
    """Normalize a plain or punctuated CPF to eleven digits.

    Raises:
        ValueError: If the input does not contain exactly eleven ASCII digits.
    """
    normalized = value.replace(".", "").replace("-", "")
    if len(normalized) != 11 or not normalized.isascii() or not normalized.isdigit():
        raise ValueError("CPF must contain exactly 11 digits")
    return normalized


class InMemoryFakeUserRepository:
    """Store fake users and credentials entirely in memory."""

    def __init__(self, users: tuple[tuple[FakeUser, SecretStr], ...] = ()) -> None:
        """Initialize the repository with unique CPF and password pairs.

        Raises:
            ValueError: If two users normalize to the same CPF.
        """
        self._users_by_cpf: dict[str, FakeUser] = {}
        self._passwords_by_cpf: dict[str, SecretStr] = {}
        for user, password in users:
            cpf = normalize_fake_cpf(user.sub)
            if cpf in self._users_by_cpf:
                raise ValueError("duplicate fake user CPF")
            self._users_by_cpf[cpf] = user.model_copy(update={"sub": cpf})
            self._passwords_by_cpf[cpf] = password

    def get(self, subject: str) -> FakeUser | None:
        """Return the user identified by a valid plain or punctuated CPF."""
        try:
            cpf = normalize_fake_cpf(subject)
        except ValueError:
            return None
        return self._users_by_cpf.get(cpf)

    def list(self) -> tuple[FakeUser, ...]:
        """Return the stored users in their insertion order."""
        return tuple(self._users_by_cpf.values())

    def authenticate(self, *, cpf: str, password: SecretStr) -> FakeUser | None:
        """Return the matching user when the supplied credentials are valid."""
        try:
            normalized = normalize_fake_cpf(cpf)
        except ValueError:
            return None
        expected = self._passwords_by_cpf.get(normalized)
        if expected is None or not compare_digest(
            expected.get_secret_value().encode("utf-8"),
            password.get_secret_value().encode("utf-8"),
        ):
            return None
        return self._users_by_cpf[normalized]


class _JsonFakeUser(BaseModel):
    """Validate an individual fake user from a JSON credential source."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    cpf: str
    password: SecretStr
    name: str
    email: str

    @field_validator("cpf")
    @classmethod
    def require_valid_cpf(cls, value: str) -> str:
        """Reject credentials whose CPF cannot identify a fake user."""
        normalize_fake_cpf(value)
        return value


class _JsonFakeUsers(BaseModel):
    """Validate the JSON document used to load fake users."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    users: tuple[_JsonFakeUser, ...]

    @field_validator("users")
    @classmethod
    def require_users(
        cls, value: tuple[_JsonFakeUser, ...]
    ) -> tuple[_JsonFakeUser, ...]:
        """Reject an empty credential source."""
        if not value:
            raise ValueError("users must contain at least one item")
        return value


class JsonFakeUserRepository:
    """Load validated fake users from a JSON file."""

    def __init__(self, repository: InMemoryFakeUserRepository) -> None:
        self._repository = repository

    @classmethod
    def from_file(cls, path: str | Path) -> "JsonFakeUserRepository":
        """Build a repository from a strict JSON credential document.

        Raises:
            ValueError: If the source is unavailable or its structure is invalid.
        """
        try:
            source = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError("fake user JSON is invalid") from None
        except OSError as error:
            raise ValueError("fake user JSON file is unavailable") from error

        try:
            records = _JsonFakeUsers.model_validate_json(source)
        except ValidationError as error:
            if any(
                issue["loc"] == ("users",) and issue["type"] == "value_error"
                for issue in error.errors()
            ):
                raise ValueError("users must contain at least one item") from None
            raise ValueError("fake user JSON is invalid") from None

        users = tuple(
            (
                FakeUser(
                    sub=normalize_fake_cpf(record.cpf),
                    name=record.name,
                    email=record.email,
                ),
                record.password,
            )
            for record in records.users
        )
        return cls(InMemoryFakeUserRepository(users))

    def get(self, subject: str) -> FakeUser | None:
        """Return the user identified by a valid plain or punctuated CPF."""
        return self._repository.get(subject)

    def list(self) -> tuple[FakeUser, ...]:
        """Return the stored users in their insertion order."""
        return self._repository.list()

    def authenticate(self, *, cpf: str, password: SecretStr) -> FakeUser | None:
        """Return the matching user when the supplied credentials are valid."""
        return self._repository.authenticate(cpf=cpf, password=password)
