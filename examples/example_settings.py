"""Application configuration used by the runnable framework examples."""

from govbr_auth.runtime import GovBrApplicationSettings


def application_settings() -> GovBrApplicationSettings:
    """Load the validated runtime and opt-in presentation settings."""
    return GovBrApplicationSettings.from_environment()
