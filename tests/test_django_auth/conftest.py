"""Fixtures for Django adapter tests."""

import os
from typing import Iterator

import django
import pytest
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_django_auth.test_settings")
django.setup()


@pytest.fixture
def client() -> Client:
    """Return a Django client that enforces CSRF checks."""
    return Client(enforce_csrf_checks=True)


@pytest.fixture(autouse=True)
def reset_fake_service_state() -> Iterator[None]:
    """Keep the module-level fake connector isolated between tests."""
    from tests.test_django_auth.test_urls import connector

    service = connector.fake_service
    if service is not None:
        service._sessions.clear()
        service._authorization_codes.clear()

    yield

    if service is not None:
        service._sessions.clear()
        service._authorization_codes.clear()
