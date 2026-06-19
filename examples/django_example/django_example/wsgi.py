"""WSGI entry point for the govbr-auth Django example."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_example.settings")

application = get_wsgi_application()
