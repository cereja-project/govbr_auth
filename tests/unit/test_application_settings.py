"""Tests for validated application-level settings."""

import pytest
from pydantic import ValidationError

from govbr_auth.runtime import (
    GovBrApplicationSettings,
    GovBrProvider,
    GovBrRuntimeSettings,
)


def test_application_settings_default_to_hidden_demo_page() -> None:
    """Omitting the opt-in flag must keep the presentation hidden."""
    settings = GovBrApplicationSettings.from_environment({"GOVBR_PROVIDER": "fake"})

    assert settings.demo_page is False
    assert settings.runtime.provider is GovBrProvider.FAKE


@pytest.mark.parametrize(
    ("configured", "expected"),
    (("true", True), ("false", False)),
)
def test_application_settings_parse_canonical_demo_page_boolean(
    configured: str,
    expected: bool,
) -> None:
    """The opt-in flag must retain only its two canonical spellings."""
    settings = GovBrApplicationSettings.from_environment(
        {
            "GOVBR_PROVIDER": "fake",
            "GOVBR_DEMO_PAGE": configured,
        }
    )

    assert settings.demo_page is expected


@pytest.mark.parametrize("configured", ("1", "yes", "TRUE", ""))
def test_application_settings_reject_noncanonical_demo_page_boolean(
    configured: str,
) -> None:
    """Truth-like values must not silently enable the demo presentation."""
    with pytest.raises(ValueError) as captured:
        GovBrApplicationSettings.from_environment(
            {
                "GOVBR_PROVIDER": "fake",
                "GOVBR_DEMO_PAGE": configured,
            }
        )

    assert str(captured.value) == (
        "Configuração Gov.br inválida: valor inválido para GOVBR_DEMO_PAGE."
    )
    if configured:
        assert configured not in str(captured.value)


def test_application_settings_are_frozen() -> None:
    """Consumers must not be able to mutate validated application settings."""
    settings = GovBrApplicationSettings(
        runtime=GovBrRuntimeSettings(provider=GovBrProvider.FAKE),
        demo_page=True,
    )

    with pytest.raises(ValidationError):
        settings.demo_page = False
