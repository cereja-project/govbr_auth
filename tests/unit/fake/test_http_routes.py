"""Unit tests for the extracted FakeGov route registration boundary."""

from datetime import UTC, datetime
from types import SimpleNamespace

from govbr_auth.fake.http.routes import build_fake_govbr_routes


class RouteProvider:
    """Minimal provider surface required by route registration."""


def test_build_fake_govbr_routes_registers_provider_endpoints() -> None:
    runtime = SimpleNamespace(
        provider=RouteProvider(),
        credential_authenticator=None,
        prefix="/fake-govbr",
    )

    router = build_fake_govbr_routes(
        runtime,
        automatic_subject=None,
        clock=lambda: datetime.now(UTC),
    )

    assert {route.path for route in router.routes} == {
        "/fake-govbr/authorize",
        "/fake-govbr/login",
        "/fake-govbr/token",
        "/fake-govbr/jwk",
        "/fake-govbr/userinfo",
    }
