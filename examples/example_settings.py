"""Provider selection used by the runnable framework examples."""

import os

from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings


def runtime_settings() -> GovBrRuntimeSettings | None:
    """Make the fake example profile explicit without weakening engine validation."""
    if os.environ.get("GOVBR_PROVIDER", "official") != GovBrProvider.FAKE:
        return None
    return GovBrRuntimeSettings(
        provider=GovBrProvider.FAKE,
        fake_end_to_end=True,
        fake_host=os.environ.get("GOVBR_FAKE_HOST", "127.0.0.1"),
        fake_port=int(os.environ.get("GOVBR_FAKE_PORT", "8000")),
    )
