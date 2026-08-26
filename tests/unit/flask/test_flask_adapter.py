"""Unit contract for the native Flask consumer adapter."""

from collections.abc import Mapping
from datetime import UTC, datetime

from flask import Flask
from pydantic import SecretStr

from govbr_auth.core.authorization import AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult
from govbr_auth.core.models import GovBrUser, TokenSet
from govbr_auth.runtime import GovBrProvider, GovBrRuntime, GovBrRuntimeSettings

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


def _runtime(client: ContractClient) -> GovBrRuntime:
    return GovBrRuntime(
        settings=GovBrRuntimeSettings(provider=GovBrProvider.OFFICIAL),
        client=client,
        provider=GovBrProvider.OFFICIAL,
        fake=None,
        _owned_http=None,
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
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
        ),
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
        settings=GovBrRuntimeSettings(
            provider=GovBrProvider.FAKE,
            fake_end_to_end=True,
        ),
        on_success=lambda context, request: ("", 204),
        clock=lambda: FIXED_NOW,
    )

    try:
        runtime = auth._owner.runtime.fake
        assert runtime is not None
        assert mounted == [(runtime, runtime.http_application, auth._clock)]
    finally:
        auth.close()
