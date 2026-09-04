"""Application configuration used by the runnable framework examples."""

from govbr_auth.runtime import GovBrRuntimeSettings


def application_settings() -> GovBrRuntimeSettings:
    """Load the validated framework-neutral runtime settings."""
    return GovBrRuntimeSettings.from_environment()
