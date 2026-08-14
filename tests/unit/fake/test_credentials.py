import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from govbr_auth.fake import (
    FakeUser,
    InMemoryFakeUserRepository,
    JsonFakeUserRepository,
)
from govbr_auth.fake.credentials import normalize_fake_cpf

ANA = FakeUser(sub="12345678901", name="Ana Demo", email="ana@example.test")


@pytest.mark.parametrize(
    "raw,expected",
    (("12345678901", "12345678901"), ("123.456.789-01", "12345678901")),
    ids=("plain-cpf", "formatted-cpf"),
)
def test_normalize_fake_cpf_accepts_plain_and_formatted_values(
    raw: str, expected: str
) -> None:
    assert normalize_fake_cpf(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ("", "123", "1234567890A", "123 456 789 01"),
    ids=("empty", "too-short", "non-digit", "contains-space"),
)
def test_normalize_fake_cpf_rejects_invalid_format(raw: str) -> None:
    with pytest.raises(ValueError, match="CPF must contain exactly 11 digits"):
        normalize_fake_cpf(raw)


def test_in_memory_repository_authenticates_valid_credentials() -> None:
    repository = InMemoryFakeUserRepository(((ANA, SecretStr("ana-demo")),))

    assert (
        repository.authenticate(cpf="123.456.789-01", password=SecretStr("ana-demo"))
        == ANA
    )


def test_in_memory_repository_rejects_invalid_password() -> None:
    repository = InMemoryFakeUserRepository(((ANA, SecretStr("ana-demo")),))

    assert (
        repository.authenticate(cpf="12345678901", password=SecretStr("wrong")) is None
    )


def test_in_memory_repository_gets_user_by_normalized_cpf() -> None:
    repository = InMemoryFakeUserRepository(((ANA, SecretStr("ana-demo")),))

    assert repository.get("12345678901") == ANA


def test_in_memory_repository_lists_users_in_insertion_order() -> None:
    repository = InMemoryFakeUserRepository(((ANA, SecretStr("ana-demo")),))

    assert repository.list() == (ANA,)


def test_in_memory_repository_repr_does_not_expose_password() -> None:
    repository = InMemoryFakeUserRepository(((ANA, SecretStr("ana-demo")),))

    assert "ana-demo" not in repr(repository)


def test_in_memory_repository_rejects_duplicate_normalized_cpf() -> None:
    duplicate = ANA.model_copy(update={"sub": "123.456.789-01"})

    with pytest.raises(ValueError, match="duplicate fake user CPF"):
        InMemoryFakeUserRepository(
            ((ANA, SecretStr("ana-demo")), (duplicate, SecretStr("other")))
        )


def test_json_repository_loads_and_authenticates(tmp_path: Path) -> None:
    source = tmp_path / "fake-users.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "12345678901",
                        "password": "ana-demo",
                        "name": "Ana Demo",
                        "email": "ana@example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repository = JsonFakeUserRepository.from_file(source)

    assert repository.authenticate(
        cpf="12345678901", password=SecretStr("ana-demo")
    ) == FakeUser(sub="12345678901", name="Ana Demo", email="ana@example.test")


@pytest.mark.parametrize(
    "payload,error",
    (
        ("not-json", "fake user JSON is invalid"),
        ('{"users": []}', "users must contain at least one item"),
        ('{"users": [{"cpf": "123"}]}', "fake user JSON is invalid"),
        (
            '{"users": [{"cpf": "123", "password": "ana-demo", "name": "Ana", "email": "ana@example.test"}]}',
            "fake user JSON is invalid",
        ),
    ),
)
def test_json_repository_rejects_invalid_content(
    tmp_path: Path, payload: str, error: str
) -> None:
    source = tmp_path / "fake-users.json"
    source.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=error) as raised:
        JsonFakeUserRepository.from_file(source)

    assert raised.value.__cause__ is None


def test_json_repository_rejects_unavailable_file(tmp_path: Path) -> None:
    source = tmp_path / "fake-users.json"

    with pytest.raises(ValueError, match="fake user JSON file is unavailable") as error:
        JsonFakeUserRepository.from_file(source)

    assert isinstance(error.value.__cause__, OSError)


def test_json_repository_rejects_extra_user_fields(tmp_path: Path) -> None:
    source = tmp_path / "fake-users.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "12345678901",
                        "password": "ana-demo",
                        "name": "Ana Demo",
                        "email": "ana@example.test",
                        "role": "admin",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fake user JSON is invalid") as raised:
        JsonFakeUserRepository.from_file(source)

    assert raised.value.__cause__ is None


def test_json_repository_gets_loaded_user_by_normalized_cpf(tmp_path: Path) -> None:
    source = tmp_path / "fake-users.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "123.456.789-01",
                        "password": "ana-demo",
                        "name": "Ana Demo",
                        "email": "ana@example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repository = JsonFakeUserRepository.from_file(source)

    user = repository.get("12345678901")

    assert user == ANA


def test_json_repository_lists_loaded_users_in_insertion_order(tmp_path: Path) -> None:
    source = tmp_path / "fake-users.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "cpf": "12345678901",
                        "password": "ana-demo",
                        "name": "Ana Demo",
                        "email": "ana@example.test",
                    },
                    {
                        "cpf": "987.654.321-00",
                        "password": "bia-demo",
                        "name": "Bia Demo",
                        "email": "bia@example.test",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    repository = JsonFakeUserRepository.from_file(source)

    users = repository.list()

    assert users == (
        ANA,
        FakeUser(sub="98765432100", name="Bia Demo", email="bia@example.test"),
    )
