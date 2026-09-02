"""Unit contract for the native Flask consumer adapter."""

from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
import pytest
from flask import Flask
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings
from govbr_auth.runtime import (
    GovBrApplicationSettings,
    GovBrProvider,
    GovBrRuntime,
    GovBrRuntimeSettings,
    create_govbr_runtime,
)

FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class ContractClient:
    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = dict(claims)
        self.tokens = TokenSet(
            access_token=SecretStr("access-token"),
            id_token=SecretStr("id-token"),
            token_type="Bearer",
            expires_in=300,
            scope="openid profile email",
        )

    def authorization_url(self, *, now: datetime) -> AuthorizationRequest:
        return AuthorizationRequest("https://sso.example.test/authorize", "state")

    async def exchange_code(
        self, *, code: str, state: str, now: datetime
    ) -> AuthenticationResult:
        return AuthenticationResult(tokens=self.tokens, id_token_claims=self.claims)

    async def userinfo(
        self, access_token: SecretStr, *, expected_subject: str
    ) -> GovBrUser:
        return GovBrUser(sub=expected_subject, name="Flask user")


def _runtime(
    client: ContractClient,
    *,
    redirect_uri: str | None = None,
) -> GovBrRuntime:
    oauth = None
    if redirect_uri is not None:
        oauth = GovBrSettings(
            authorization_url="https://sso.example.test/authorize",
            token_url="https://sso.example.test/token",
            userinfo_url="https://sso.example.test/userinfo",
            client_id="client-id",
            client_secret=SecretStr("client-secret"),
            redirect_uri=redirect_uri,
            transaction_secret=SecretStr("transaction-secret"),
            issuer="https://sso.example.test/",
            jwks_url="https://sso.example.test/jwks",
        )
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL, oauth=oauth),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=None,
    )


def _fake_application_settings(*, demo_page: bool = False) -> GovBrApplicationSettings:
    return GovBrApplicationSettings(
        runtime=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
        ),
        demo_page=demo_page,
    )


def _colliding_fake_runtime() -> GovBrRuntime:
    return create_govbr_runtime(
        GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_provider_prefix="/auth/govbr",
        ),
        fake_transport_factory=lambda _: httpx.MockTransport(
            lambda __: httpx.Response(500)
        ),
        clock=lambda: FIXED_NOW,
    )


def test_flask_facade_exposes_a_blueprint_with_consumer_routes() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )

    application = Flask(__name__)
    application.register_blueprint(auth.blueprint)
    paths = {rule.rule for rule in application.url_map.iter_rules()}

    assert {"/auth/govbr/login", "/auth/govbr/callback"} <= paths


def test_flask_facade_mounts_callback_at_configured_redirect_uri_path() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(
            ContractClient({"sub": "subject"}),
            redirect_uri=(
                "https://staging.example.test/oauth/govbr/caf%C3%A9%20retorno"
            ),
        ),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    application.register_blueprint(auth.blueprint)

    paths = {rule.rule for rule in application.url_map.iter_rules()}
    assert "/auth/govbr/login" in paths
    assert "/oauth/govbr/café retorno" in paths
    assert "/auth/govbr/callback" not in paths
    callback = application.test_client().get("/oauth/govbr/caf%C3%A9%20retorno")
    assert callback.status_code == 400


def test_flask_login_redirects_using_the_core_authorization_url() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    application.register_blueprint(auth.blueprint)

    response = application.test_client().get("/auth/govbr/login")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://sso.example.test/authorize"


def test_flask_callback_passes_context_and_native_request_to_success_handler() -> None:
    from govbr_auth.flask import GovBrAuth

    received: list[tuple[object, str]] = []

    def on_success(context, request):
        received.append((context, request.path))
        return "", 204

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=on_success,
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    application.register_blueprint(auth.blueprint)

    response = application.test_client().get(
        "/auth/govbr/callback?code=code&state=state"
    )

    assert response.status_code == 204
    assert received[0][0].user.subject == "subject"
    assert received[0][1] == "/auth/govbr/callback"


def test_flask_fake_runtime_adds_provider_routes() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        settings=_fake_application_settings(),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    auth.register(application)

    try:
        paths = {rule.rule for rule in application.url_map.iter_rules()}
        assert {
            "/auth/govbr/login",
            "/auth/govbr/callback",
            "/fake-govbr/authorize",
            "/fake-govbr/login",
            "/fake-govbr/token",
            "/fake-govbr/jwk",
            "/fake-govbr/userinfo",
        } <= paths
    finally:
        auth.close()


def test_flask_fake_runtime_passes_simulator_http_application_to_provider_blueprint(
    monkeypatch,
) -> None:
    import govbr_auth.flask as flask_adapter
    from govbr_auth.flask import GovBrAuth

    mounted: list[tuple[object, object, object]] = []

    def create_blueprint(runtime, *, application, clock):
        mounted.append((runtime, application, clock))
        from flask import Blueprint

        return Blueprint("fake_govbr", __name__)

    monkeypatch.setattr(
        flask_adapter,
        "create_fake_govbr_blueprint",
        create_blueprint,
    )

    auth = GovBrAuth(
        settings=_fake_application_settings(),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )

    try:
        runtime = auth._owner.runtime.fake
        assert runtime is not None
        assert mounted == [(runtime, runtime.http_application, auth._clock)]
    finally:
        auth.close()


def test_flask_demo_page_is_absent_by_default_for_borrowed_runtime() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    auth.register(application)

    assert application.test_client().get("/govbr-auth-demo").status_code == 404


def test_flask_demo_page_is_opt_in_with_native_response() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        runtime=_runtime(ContractClient({"sub": "subject"})),
        demo_page=True,
        prefix="/oauth/govbr",
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    auth.register(application)

    response = application.test_client().get("/govbr-auth-demo")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Type"].startswith("text/html")
    assert "Provedor oficial Gov.br" in response.text
    assert 'href="/oauth/govbr/login"' in response.text


def test_flask_fake_settings_without_demo_page_keep_provider_routes() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        settings=_fake_application_settings(),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    auth.register(application)

    try:
        paths = {rule.rule for rule in application.url_map.iter_rules()}
        assert "/govbr-auth-demo" not in paths
        assert "/fake-govbr/login" in paths
    finally:
        auth.close()


def test_flask_fake_settings_can_publish_credential_free_demo_page() -> None:
    from govbr_auth.flask import GovBrAuth

    auth = GovBrAuth(
        settings=_fake_application_settings(demo_page=True),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    auth.register(application)

    try:
        response = application.test_client().get("/govbr-auth-demo")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Content-Type"].startswith("text/html")
        assert "FakeGov" in response.text
        assert "Não use credenciais reais." in response.text
        assert "11122233344" not in response.text
        assert "senha-ficticia" not in response.text
    finally:
        auth.close()


def test_flask_demo_page_argument_conflicts_with_application_settings() -> None:
    from govbr_auth.flask import GovBrAuth

    with pytest.raises(TypeError, match="demo_page must be configured in settings"):
        GovBrAuth(
            settings=_fake_application_settings(),
            demo_page=True,
            on_success=lambda context, request: ("", 204),
            clock=lambda: FIXED_NOW,
        )


def test_flask_direct_demo_page_rejects_before_environment_or_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import govbr_auth.adapters._runtime as adapter_runtime
    from govbr_auth.flask import GovBrAuth

    environment_reads: list[object] = []
    runtime_allocations: list[object] = []

    def load_environment() -> GovBrApplicationSettings:
        environment_reads.append(object())
        return GovBrApplicationSettings(
            runtime=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL)
        )

    def allocate_runtime(*args, **kwargs) -> GovBrRuntime:
        runtime_allocations.append((args, kwargs))
        return _runtime(ContractClient({"sub": "subject"}))

    monkeypatch.setattr(
        adapter_runtime.GovBrApplicationSettings,
        "from_environment",
        load_environment,
    )
    monkeypatch.setattr(adapter_runtime, "create_govbr_runtime", allocate_runtime)

    captured_error = None
    try:
        GovBrAuth(
            demo_page=True,
            on_success=lambda context, request: ("", 204),
            clock=lambda: FIXED_NOW,
        )
    except TypeError as error:
        captured_error = error

    assert (environment_reads, runtime_allocations) == ([], [])
    assert str(captured_error) == "demo_page must be configured in settings"


def test_flask_demo_page_rejects_callback_collision_only_when_enabled() -> None:
    from govbr_auth.flask import GovBrAuth

    runtime = _runtime(
        ContractClient({"sub": "subject"}),
        redirect_uri="https://consumer.example.test/govbr-auth-demo",
    )
    auth = GovBrAuth(
        runtime=runtime,
        demo_page=False,
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )
    application = Flask(__name__)
    auth.register(application)

    assert application.test_client().get("/govbr-auth-demo").status_code == 400
    with pytest.raises(
        ValueError,
        match="redirect URI callback path must differ from the demo page path",
    ):
        GovBrAuth(
            runtime=runtime,
            demo_page=True,
            on_success=lambda context, request: ("", 204),
            clock=lambda: FIXED_NOW,
        )


def test_flask_rejects_owned_fake_prefix_collision() -> None:
    from govbr_auth.flask import GovBrAuth

    settings = GovBrApplicationSettings(
        runtime=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_provider_prefix="/auth/govbr",
        )
    )
    auth = None

    try:
        with pytest.raises(
            ValueError,
            match="o prefixo do FakeGov deve ser diferente do prefixo do adapter",
        ):
            auth = GovBrAuth(
                settings=settings,
                on_success=lambda context, request: ("", 204),
                clock=lambda: FIXED_NOW,
            )
    finally:
        if auth is not None:
            auth.close()


def test_flask_rejects_borrowed_fake_prefix_collision() -> None:
    from govbr_auth.adapters._sync import run_sync
    from govbr_auth.flask import GovBrAuth

    runtime = _colliding_fake_runtime()

    try:
        with pytest.raises(
            ValueError,
            match="o prefixo do FakeGov deve ser diferente do prefixo do adapter",
        ):
            GovBrAuth(
                runtime=runtime,
                on_success=lambda context, request: ("", 204),
                clock=lambda: FIXED_NOW,
            )
    finally:
        run_sync(runtime.aclose)
