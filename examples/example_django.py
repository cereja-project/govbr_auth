"""Django URL configuration using the synchronous govbr-auth adapter."""

from django.http import JsonResponse

from examples.example_settings import runtime_settings
from govbr_auth.django import GovBrAuth


def authenticated(context, request):
    """Return a minimal success response to the host Django application."""
    return JsonResponse({"authenticated": True})


auth = GovBrAuth(on_success=authenticated, settings=runtime_settings())
urlpatterns = auth.urlpatterns
