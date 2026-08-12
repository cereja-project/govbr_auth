"""Tests for the asynchronous Gov.br OAuth HTTP client."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from govbr_auth.core.client import AuthenticationResult, GovBrClient
from govbr_auth.core.errors import (
    GovBrAuthError,
    InvalidIdTokenError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from govbr_auth.core.models import AuthTransaction
from govbr_auth.core.settings import GovBrSettings

FIXED_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
SENSITIVE_CODE = "sensitive-authorization-code"
SENSITIVE_STATE = "sensitive-oauth-state"
SENSITIVE_ACCESS_TOKEN = "sensitive-access-token"
SENSITIVE_ID_TOKEN = "sensitive-id-token"
SENSITIVE_JWK = "sensitive-jwk-material"
SENSITIVE_CLIENT_SECRET = "sensitive-client-secret"
VALIDATED_SUBJECT = "12345678900"
SUBSTITUTED_SUBJECT = "98765432100"


class RecordingTransactionStore:
    """Return one deterministic transaction and record transaction operations."""

    def __init__(self) -> None:
        self.transaction = AuthTransaction(
            transaction_id="transaction-123",
            code_verifier=SecretStr("sensitive-code-verifier"),
            nonce=SecretStr("sensitive-expected-nonce"),
            issued_at=FIXED_NOW,
            expires_at=FIXED_NOW + timedelta(minutes=5),
        )
        self.consume_calls: list[tuple[str, datetime]] = []

    def create(self, *, now: datetime) -> tuple[str, AuthTransaction]:
        return SENSITIVE_STATE, self.transaction

    def consume(self, state: str, *, now: datetime) -> AuthTransaction:
        self.consume_calls.append((state, now))
        return self.transaction


class RecordingIdTokenValidator:
    """Return deterministic claims and record the security binding inputs."""

    def __init__(self, *, error: InvalidIdTokenError | None = None) -> None:
        self.error = error
        self.calls: list[
            tuple[SecretStr, SecretStr, Mapping[str, object], datetime]
        ] = []

    def validate(
        self,
        id_token: SecretStr,
        expected_nonce: SecretStr,
        *,
        jwks: Mapping[str, object],
        now: datetime,
    ) -> Mapping[str, object]:
        self.calls.append((id_token, expected_nonce, jwks, now))
        if self.error is not None:
            raise self.error
        return {
            "sub": "12345678900",
            "nonce": expected_nonce.get_secret_value(),
        }


@pytest.fixture
def settings() -> GovBrSettings:
    return GovBrSettings(
        authorization_url="https://sso.example.test/authorize",
        token_url="https://sso.example.test/token",
        userinfo_url="https://sso.example.test/userinfo",
        client_id="test-client",
        client_secret=SecretStr(SENSITIVE_CLIENT_SECRET),
        redirect_uri="https://consumer.example.test/oauth/callback",
        transaction_secret=SecretStr("sensitive-transaction-secret"),
        issuer="https://sso.example.test",
        jwks_url="https://sso.example.test/jwk",
        connect_timeout_seconds=2,
        read_timeout_seconds=3,
    )


def _token_response() -> dict[str, object]:
    return {
        "access_token": SENSITIVE_ACCESS_TOKEN,
        "id_token": SENSITIVE_ID_TOKEN,
        "token_type": "Bearer",
        "expires_in": 300,
        "scope": "openid profile email",
    }


def _jwks_response() -> dict[str, object]:
    return {"keys": [{"kid": "provider-rsa-key"}]}


def _assert_error_is_sanitized(error: BaseException) -> None:
    messages: list[str] = []
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        messages.append(str(current))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    rendered = " ".join(messages)

    assert SENSITIVE_CODE not in rendered
    assert SENSITIVE_STATE not in rendered
    assert SENSITIVE_ACCESS_TOKEN not in rendered
    assert SENSITIVE_ID_TOKEN not in rendered
    assert SENSITIVE_JWK not in rendered
    assert SENSITIVE_CLIENT_SECRET not in rendered
    assert VALIDATED_SUBJECT not in rendered
    assert SUBSTITUTED_SUBJECT not in rendered


def _assert_safe_cause(
    error: GovBrAuthError,
    *,
    cause_type: type[BaseException],
    cause_message: str,
) -> None:
    assert isinstance(error.__cause__, cause_type)
    assert str(error.__cause__) == cause_message
    _assert_error_is_sanitized(error)


@pytest.mark.asyncio
async def test_exchange_code_returns_tokens_and_claims_after_single_state_consumption(
    settings: GovBrSettings,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json=_jwks_response())

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        result = await client.exchange_code(
            code=SENSITIVE_CODE,
            state=SENSITIVE_STATE,
            now=FIXED_NOW,
        )

    assert isinstance(result, AuthenticationResult)
    assert result.tokens.access_token.get_secret_value() == SENSITIVE_ACCESS_TOKEN
    assert result.id_token_claims == {
        "sub": "12345678900",
        "nonce": "sensitive-expected-nonce",
    }
    assert transactions.consume_calls == [(SENSITIVE_STATE, FIXED_NOW)]
    validated_token, validated_nonce, validated_jwks, validated_now = validator.calls[0]
    assert validated_token.get_secret_value() == SENSITIVE_ID_TOKEN
    assert validated_nonce.get_secret_value() == "sensitive-expected-nonce"
    assert validated_jwks == _jwks_response()
    assert validated_now == FIXED_NOW
    assert [(request.method, request.url) for request in requests] == [
        ("POST", httpx.URL("https://sso.example.test/token")),
        ("GET", httpx.URL("https://sso.example.test/jwk")),
    ]
    assert requests[1].extensions["timeout"] == {
        "connect": 2.0,
        "read": 3.0,
        "write": 3.0,
        "pool": 2.0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport_error", "expected_message", "expected_cause"),
    [
        pytest.param(
            httpx.ReadTimeout,
            "Gov.br provider request timed out",
            "Gov.br HTTP transport failed (ReadTimeout)",
            id="timeout",
        ),
        pytest.param(
            httpx.ConnectError,
            "Gov.br provider request failed",
            "Gov.br HTTP transport failed (ConnectError)",
            id="transport",
        ),
    ],
)
async def test_exchange_code_sanitizes_jwks_transport_failures(
    transport_error: type[httpx.TransportError],
    expected_message: str,
    expected_cause: str,
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        raise transport_error(SENSITIVE_JWK, request=request)

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            ProviderUnavailableError,
            match=expected_message,
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    assert validator.calls == []
    _assert_safe_cause(
        error.value,
        cause_type=RuntimeError,
        cause_message=expected_cause,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_message", "expected_error_type"),
    [
        pytest.param(
            400,
            "Gov.br rejected the JWKS request",
            ProviderRejectedError,
            id="rejected",
        ),
        pytest.param(
            500,
            "Gov.br provider request failed",
            ProviderUnavailableError,
            id="unavailable",
        ),
    ],
)
async def test_exchange_code_sanitizes_jwks_error_statuses(
    status_code: int,
    expected_message: str,
    expected_error_type: type[GovBrAuthError],
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        return httpx.Response(status_code, text=SENSITIVE_JWK)

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(expected_error_type, match=expected_message) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    assert validator.calls == []
    _assert_safe_cause(
        error.value,
        cause_type=RuntimeError,
        cause_message=f"Gov.br provider returned HTTP status {status_code}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "failure_type"),
    [
        pytest.param(
            f"not-json {SENSITIVE_JWK}".encode(),
            "JSONDecodeError",
            id="invalid_json",
        ),
        pytest.param(
            b"\xff" + SENSITIVE_JWK.encode(),
            "UnicodeDecodeError",
            id="invalid_unicode",
        ),
    ],
)
async def test_exchange_code_rejects_invalid_jwks_encoding_without_exposure(
    content: bytes,
    failure_type: str,
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, content=content)

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br JWKS response is invalid",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    assert validator.calls == []
    _assert_safe_cause(
        error.value,
        cause_type=ValueError,
        cause_message=f"Gov.br response validation failed ({failure_type})",
    )


@pytest.mark.asyncio
async def test_exchange_code_rejects_non_mapping_jwks_response(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json=[{"keys": [SENSITIVE_JWK]}])

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br JWKS response is invalid",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    assert validator.calls == []
    _assert_safe_cause(
        error.value,
        cause_type=ValueError,
        cause_message="Gov.br response validation failed (InvalidJwks)",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing_keys"),
        pytest.param({"keys": []}, id="empty_keys"),
        pytest.param({"keys": SENSITIVE_JWK}, id="non_list_keys"),
        pytest.param({"keys": [SENSITIVE_JWK]}, id="non_mapping_key"),
        pytest.param({"keys": [{}]}, id="empty_key"),
    ],
)
async def test_exchange_code_rejects_empty_or_malformed_jwks_keys(
    payload: object,
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json=payload)

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br JWKS response is invalid",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    assert validator.calls == []
    _assert_safe_cause(
        error.value,
        cause_type=ValueError,
        cause_message="Gov.br response validation failed (InvalidJwks)",
    )


@pytest.mark.asyncio
async def test_authorization_url_uses_bound_authorization_builder(
    settings: GovBrSettings,
) -> None:
    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as http:
        client = GovBrClient(settings, transactions, validator, http)

        request = client.authorization_url(now=FIXED_NOW)

    assert request.state == SENSITIVE_STATE
    assert "nonce=sensitive-expected-nonce" in request.url
    assert "code_challenge_method=S256" in request.url


@pytest.mark.asyncio
async def test_userinfo_uses_bearer_token_and_returns_strict_user(
    settings: GovBrSettings,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"sub": "12345678900", "email_verified": True},
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        user = await client.userinfo(
            SecretStr(SENSITIVE_ACCESS_TOKEN),
            expected_subject=VALIDATED_SUBJECT,
        )

    request = requests[0]
    assert user.sub == "12345678900"
    assert user.email_verified is True
    assert request.method == "GET"
    assert request.url == httpx.URL("https://sso.example.test/userinfo")
    assert request.headers["authorization"] == f"Bearer {SENSITIVE_ACCESS_TOKEN}"


@pytest.mark.asyncio
async def test_userinfo_rejects_subject_not_bound_to_validated_id_token(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sub": SUBSTITUTED_SUBJECT})

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br userinfo response is invalid",
        ) as error:
            await client.userinfo(
                SecretStr(SENSITIVE_ACCESS_TOKEN),
                expected_subject=VALIDATED_SUBJECT,
            )

    _assert_safe_cause(
        error.value,
        cause_type=ValueError,
        cause_message="Gov.br response validation failed (SubjectMismatch)",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport_error", "expected_message", "expected_cause", "expected_error_type"),
    [
        pytest.param(
            httpx.ReadTimeout,
            "Gov.br provider request timed out",
            "Gov.br HTTP transport failed (ReadTimeout)",
            ProviderUnavailableError,
            id="timeout",
        ),
        pytest.param(
            httpx.ConnectError,
            "Gov.br provider request failed",
            "Gov.br HTTP transport failed (ConnectError)",
            ProviderUnavailableError,
            id="transport",
        ),
    ],
)
async def test_userinfo_sanitizes_transport_failures(
    transport_error: type[httpx.TransportError],
    expected_message: str,
    expected_cause: str,
    expected_error_type: type[GovBrAuthError],
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise transport_error(
            f"{SENSITIVE_ACCESS_TOKEN} {SUBSTITUTED_SUBJECT}",
            request=request,
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(expected_error_type, match=expected_message) as error:
            await client.userinfo(
                SecretStr(SENSITIVE_ACCESS_TOKEN),
                expected_subject=VALIDATED_SUBJECT,
            )

    _assert_safe_cause(
        error.value,
        cause_type=RuntimeError,
        cause_message=expected_cause,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_message", "expected_error_type"),
    [
        pytest.param(
            400,
            "Gov.br rejected the access token",
            ProviderRejectedError,
            id="bad_request",
        ),
        pytest.param(
            401,
            "Gov.br rejected the access token",
            ProviderRejectedError,
            id="unauthorized",
        ),
        pytest.param(
            403,
            "Gov.br rejected the access token",
            ProviderRejectedError,
            id="forbidden",
        ),
        pytest.param(
            500,
            "Gov.br provider request failed",
            ProviderUnavailableError,
            id="server_error",
        ),
    ],
)
async def test_userinfo_sanitizes_provider_error_statuses(
    status_code: int,
    expected_message: str,
    expected_error_type: type[GovBrAuthError],
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text=f"{SENSITIVE_ACCESS_TOKEN} {SUBSTITUTED_SUBJECT}",
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(expected_error_type, match=expected_message) as error:
            await client.userinfo(
                SecretStr(SENSITIVE_ACCESS_TOKEN),
                expected_subject=VALIDATED_SUBJECT,
            )

    _assert_safe_cause(
        error.value,
        cause_type=RuntimeError,
        cause_message=f"Gov.br provider returned HTTP status {status_code}",
    )


@pytest.mark.asyncio
async def test_userinfo_rejects_invalid_json_with_safe_causal_chain(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=f"not-json {SENSITIVE_ACCESS_TOKEN} {SUBSTITUTED_SUBJECT}",
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br userinfo response is invalid",
        ) as error:
            await client.userinfo(
                SecretStr(SENSITIVE_ACCESS_TOKEN),
                expected_subject=VALIDATED_SUBJECT,
            )

    _assert_safe_cause(
        error.value,
        cause_type=ValueError,
        cause_message="Gov.br response validation failed (JSONDecodeError)",
    )


@pytest.mark.asyncio
async def test_userinfo_rejects_invalid_schema_with_safe_causal_chain(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"name": SUBSTITUTED_SUBJECT},
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br userinfo response is invalid",
        ) as error:
            await client.userinfo(
                SecretStr(SENSITIVE_ACCESS_TOKEN),
                expected_subject=VALIDATED_SUBJECT,
            )

    _assert_safe_cause(
        error.value,
        cause_type=ValueError,
        cause_message="Gov.br response validation failed (ValidationError)",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport_error", "expected_message", "expected_error_type"),
    [
        pytest.param(
            httpx.ReadTimeout,
            "Gov.br provider request timed out",
            ProviderUnavailableError,
            id="timeout",
        ),
        pytest.param(
            httpx.ConnectError,
            "Gov.br provider request failed",
            ProviderUnavailableError,
            id="transport",
        ),
    ],
)
async def test_exchange_code_sanitizes_transport_failures(
    transport_error: type[httpx.TransportError],
    expected_message: str,
    expected_error_type: type[GovBrAuthError],
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise transport_error(SENSITIVE_CODE, request=request)

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(expected_error_type, match=expected_message) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    _assert_error_is_sanitized(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [
        pytest.param(400, id="bad_request"),
        pytest.param(401, id="unauthorized"),
        pytest.param(403, id="forbidden"),
    ],
)
async def test_exchange_code_classifies_client_error_responses_as_provider_rejections(
    status_code: int,
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": "invalid_grant",
                "error_description": (
                    f"rejected {SENSITIVE_CODE} {SENSITIVE_STATE} "
                    f"{SENSITIVE_ACCESS_TOKEN} {SENSITIVE_CLIENT_SECRET}"
                ),
            },
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            ProviderRejectedError,
            match="Gov.br rejected the authorization code",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    _assert_error_is_sanitized(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [
        pytest.param(408, id="request_timeout"),
        pytest.param(429, id="too_many_requests"),
    ],
)
async def test_exchange_code_classifies_temporary_client_errors_as_provider_unavailable(
    status_code: int,
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=SENSITIVE_ACCESS_TOKEN)

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            ProviderUnavailableError,
            match="Gov.br provider request failed",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    _assert_error_is_sanitized(error.value)


@pytest.mark.asyncio
async def test_exchange_code_sanitizes_provider_server_error(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text=f"{SENSITIVE_ACCESS_TOKEN} {SENSITIVE_ID_TOKEN}",
        )

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            ProviderUnavailableError,
            match="Gov.br provider request failed",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    _assert_error_is_sanitized(error.value)


@pytest.mark.asyncio
async def test_exchange_code_rejects_invalid_json_without_exposing_body(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"not-json {SENSITIVE_ACCESS_TOKEN}")

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br token response is invalid",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    _assert_error_is_sanitized(error.value)


@pytest.mark.asyncio
async def test_exchange_code_rejects_missing_token_fields(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": SENSITIVE_ACCESS_TOKEN})

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            GovBrAuthError,
            match="Gov.br token response is invalid",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    _assert_error_is_sanitized(error.value)


@pytest.mark.asyncio
async def test_exchange_code_propagates_invalid_id_token_after_consuming_state_once(
    settings: GovBrSettings,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == str(settings.token_url):
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json=_jwks_response())

    transactions = RecordingTransactionStore()
    validator = RecordingIdTokenValidator(
        error=InvalidIdTokenError("ID token validation failed")
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GovBrClient(settings, transactions, validator, http)

        with pytest.raises(
            InvalidIdTokenError,
            match="ID token validation failed",
        ) as error:
            await client.exchange_code(
                code=SENSITIVE_CODE,
                state=SENSITIVE_STATE,
                now=FIXED_NOW,
            )

    assert transactions.consume_calls == [(SENSITIVE_STATE, FIXED_NOW)]
    _assert_error_is_sanitized(error.value)
