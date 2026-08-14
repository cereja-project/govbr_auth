import pytest
from pydantic import SecretStr

from govbr_auth.fake import FakeUser, InMemoryFakeUserRepository
from govbr_auth.fake.credentials import normalize_fake_cpf

ANA = FakeUser(sub="12345678901", name="Ana Demo", email="ana@example.test")


@pytest.mark.parametrize(
    "raw,expected",
    (("12345678901", "12345678901"), ("123.456.789-01", "12345678901")),
)
def test_normalize_fake_cpf_accepts_plain_and_formatted_values(
    raw: str, expected: str
) -> None:
    assert normalize_fake_cpf(raw) == expected


@pytest.mark.parametrize("raw", ("", "123", "1234567890A", "123 456 789 01"))
def test_normalize_fake_cpf_rejects_invalid_format(raw: str) -> None:
    with pytest.raises(ValueError, match="CPF must contain exactly 11 digits"):
        normalize_fake_cpf(raw)


def test_in_memory_repository_authenticates_without_exposing_password() -> None:
    repository = InMemoryFakeUserRepository(((ANA, SecretStr("ana-demo")),))

    assert (
        repository.authenticate(cpf="123.456.789-01", password=SecretStr("ana-demo"))
        == ANA
    )
    assert (
        repository.authenticate(cpf="12345678901", password=SecretStr("wrong")) is None
    )
    assert repository.get("12345678901") == ANA
    assert repository.list() == (ANA,)
    assert "ana-demo" not in repr(repository)


def test_in_memory_repository_rejects_duplicate_normalized_cpf() -> None:
    duplicate = ANA.model_copy(update={"sub": "123.456.789-01"})

    with pytest.raises(ValueError, match="duplicate fake user CPF"):
        InMemoryFakeUserRepository(
            ((ANA, SecretStr("ana-demo")), (duplicate, SecretStr("other")))
        )
