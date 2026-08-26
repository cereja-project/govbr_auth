"""Django example that keeps the same consumer runtime across providers."""

from django.http import JsonResponse

from examples.example_settings import runtime_settings
from govbr_auth.django import GovBrAuth


def authenticated(context, request):
    """Return a minimal success response to the host Django application."""
    return JsonResponse({"authenticated": True})


# The Django consumer stays the same; fake mode changes only provider wiring.
auth = GovBrAuth(on_success=authenticated, settings=runtime_settings())
urlpatterns = auth.urlpatterns
