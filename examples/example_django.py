"""Django URL configuration using the synchronous govbr-auth adapter."""

from django.http import JsonResponse

from govbr_auth.django import GovBrAuth


def authenticated(context, request):
    """Return the authenticated subject to the host Django application."""
    return JsonResponse({"authenticated": True, "subject": context.user.subject})


auth = GovBrAuth(on_success=authenticated)
urlpatterns = auth.urlpatterns
