"""Django example that keeps the same consumer runtime across providers."""

from pathlib import Path

from dotenv import load_dotenv
from django.http import JsonResponse

from examples.example_settings import runtime_settings
from govbr_auth.django import GovBrAuth
from govbr_auth.runtime import GovBrApplicationSettings

load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def authenticated(context, request):
    """Return a minimal success response to the host Django application."""
    return JsonResponse({"authenticated": True})


# The Django consumer stays the same; fake mode changes only provider wiring.
auth = GovBrAuth(
    on_success=authenticated,
    settings=GovBrApplicationSettings(runtime=runtime_settings()),
)
urlpatterns = auth.urlpatterns
