"""Validated application-level configuration for Gov.br adapters."""

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from govbr_auth.runtime_settings import (
    GovBrRuntimeSettings,
    _configuration_error_message,
)


class GovBrApplicationSettings(BaseModel):
    """Combine the neutral runtime with opt-in adapter presentation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    runtime: GovBrRuntimeSettings
    demo_page: bool = False

    @field_validator("demo_page", mode="before")
    @classmethod
    def validate_demo_page(cls, value: object) -> bool:
        """Accept only canonical demo-page boolean spellings."""
        if isinstance(value, bool):
            return value
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("must be 'true' or 'false'")

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "GovBrApplicationSettings":
        """Build application settings from an explicit environment mapping."""
        values = dict(os.environ if environ is None else environ)
        demo_page = values.pop("GOVBR_DEMO_PAGE", None)
        payload: dict[str, object] = {
            "runtime": GovBrRuntimeSettings.from_environment(values)
        }
        if demo_page is not None:
            payload["demo_page"] = demo_page
        try:
            return cls.model_validate(payload)
        except ValidationError as error:
            raise ValueError(_configuration_error_message(error)) from None
