import os
import django
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_django_auth.test_settings")
django.setup()

def test_get_url():
    client = Client()
    response = client.get("/auth/govbr/authorize")
    assert response.status_code == 200
