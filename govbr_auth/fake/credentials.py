"""Credential sources for the explicit local Fake Gov.br provider."""

from secrets import compare_digest
from typing import Protocol

from pydantic import SecretStr

from govbr_auth.fake.models import FakeUser


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
            expected.get_secret_value(), password.get_secret_value()
        ):
            return None
        return self._users_by_cpf[normalized]
