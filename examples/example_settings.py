"""Provider selection used by the runnable framework examples."""

from govbr_auth.runtime import GovBrRuntimeSettings


def runtime_settings() -> GovBrRuntimeSettings:
    """Load the complete validated environment used by the public adapters."""
    return GovBrRuntimeSettings.from_environment()
