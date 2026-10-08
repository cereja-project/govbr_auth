"""Keep repeated login requests compatible with endpoint instrumentation."""

from functools import wraps
from inspect import iscoroutinefunction

from fastapi import routing
from fastapi.testclient import TestClient
import pytest

from govbr_auth.fake import create_fake_app
from govbr_auth.runtime import GovBrRuntimeSettings


def test_repeated_login_does_not_accumulate_endpoint_instrumentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy instrumentation wraps dependant.call when a handler is built."""
    original_handler = routing.get_request_handler
    invocations = []

    def instrument_handler(*args, **kwargs):
        dependant = kwargs["dependant"]
        endpoint = dependant.call
        if iscoroutinefunction(endpoint):

            @wraps(endpoint)
            async def instrumented(*endpoint_args, **endpoint_kwargs):
                invocations.append(endpoint.__name__)
                return await endpoint(*endpoint_args, **endpoint_kwargs)

            dependant.call = instrumented
        return original_handler(*args, **kwargs)

    monkeypatch.setattr(routing, "get_request_handler", instrument_handler)
    app = create_fake_app(
        GovBrRuntimeSettings.from_environment({"GOVBR_PROVIDER": "fake"})
    )
    with TestClient(app) as client:
        for _ in range(3):
            invocations.clear()
            response = client.get("/auth/govbr/login", follow_redirects=False)
            assert response.status_code == 302
            assert invocations == ["login"]
