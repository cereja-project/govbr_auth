"""End-to-end FakeGov authentication through the native Flask adapter."""

from datetime import UTC, datetime
import re
from urllib.parse import urlsplit

from flask import Flask, jsonify

from govbr_auth.flask import GovBrAuth
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

FIXED_NOW = datetime(2026, 8, 25, 12, tzinfo=UTC)


def _path(location: str) -> str:
    parsed = urlsplit(location)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def test_flask_fake_runtime_completes_browser_authentication_flow() -> None:
    received: list[str] = []
    application = Flask(__name__)

    def authenticated(context, request):
        received.append(context.user.subject)
        return jsonify({"authenticated": True})

    auth = GovBrAuth(
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
        ),
        on_success=authenticated,
        clock=lambda: FIXED_NOW,
    )
    auth.register(application)

    try:
        client = application.test_client()
        login = client.get("/auth/govbr/login")
        authorize = client.get(_path(login.headers["Location"]))
        request_value = re.search(
            r'name="request" value="([^"]+)"', authorize.text
        ).group(1)
        fake_login = client.post(
            "/fake-govbr/login",
            data={
                "request": request_value,
                "cpf": "12345678901",
                "password": "ana-demo",
            },
        )
        callback = client.get(_path(fake_login.headers["Location"]))

        assert login.status_code == 302
        assert authorize.status_code == 200
        assert fake_login.status_code == 302
        assert callback.status_code == 200
        assert callback.json == {"authenticated": True}
        assert received == ["12345678901"]
    finally:
        auth.close()
