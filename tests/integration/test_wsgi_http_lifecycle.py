"""Real pooled HTTP connections across successive synchronous authentications."""

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
import uvicorn
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa

from govbr_auth.core.settings import GovBrSettings
from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings
from tests.integration.browser_support import browser_application
from tests.integration.core.provider import GovBrAsgiProvider

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


@contextmanager
def socket_provider():
    """Expose the independent RS256 test provider over TCP, not MockTransport."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        provider = GovBrAsgiProvider(
            signing_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
            now=NOW,
            base_url=f"http://127.0.0.1:{sock.getsockname()[1]}",
        )
        connections = []

        async def app(scope, receive, send):
            if scope["type"] == "http":
                connections.append(scope["client"])
            await provider(scope, receive, send)

        server = uvicorn.Server(
            uvicorn.Config(
                app, lifespan="off", log_level="error", timeout_keep_alive=30
            )
        )
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline
                time.sleep(0.01)
            yield provider, connections
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


@pytest.mark.parametrize("framework", ("django", "flask"))
@pytest.mark.parametrize("concurrent", (False, True))
def test_wsgi_adapter_reuses_keepalive_on_the_same_live_event_loop(
    framework, concurrent
):
    with socket_provider() as (provider, connections):
        settings = GovBrRuntimeSettings(
            provider=GovBrProvider.OFFICIAL,
            oauth=GovBrSettings(
                environment="local",
                authorization_url=provider.authorization_url,
                token_url=f"{provider.base_url}/token",
                userinfo_url=f"{provider.base_url}/userinfo",
                client_id=provider.client_id,
                client_secret=provider.client_secret,
                redirect_uri=provider.redirect_uri,
                transaction_secret=Fernet.generate_key().decode("ascii"),
                issuer=provider.issuer,
                jwks_url=f"{provider.base_url}/jwk",
            ),
        )
        with browser_application(framework, settings, clock=lambda: NOW) as (
            auth,
            browser,
            received,
        ):

            def authenticate(_):
                client = browser()
                login = client("/auth/govbr/login")
                location = login.headers["location"]
                state = parse_qs(urlsplit(location).query)["state"][0]
                code = provider.authorize(location)
                callback = client(
                    "/callback?" + urlencode({"state": state, "code": code})
                )
                assert callback.status_code == 200

            if concurrent:
                with ThreadPoolExecutor(max_workers=3) as workers:
                    list(workers.map(authenticate, range(3)))
            else:
                for attempt in range(3):
                    authenticate(attempt)
            assert received == ["12345678900"] * 3
            assert len(connections) == 9
            if not concurrent:
                assert len(set(connections)) == 1

        assert auth._application.runtime.is_closed
        assert auth._application.runtime._owned_http.is_closed
