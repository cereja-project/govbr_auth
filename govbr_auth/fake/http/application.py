"""Framework-neutral HTTP use cases for the local FakeGov provider."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from pydantic import SecretStr

from govbr_auth.fake.credentials import FakeCredentialAuthenticator
from govbr_auth.fake.http.parsing import (
    parse_basic_authorization,
    parse_bearer_authorization,
    required_text_values,
)
from govbr_auth.fake.models import FakeUser
from govbr_auth.fake.provider import (
    FakeAuthorizationRedirect,
    FakeAuthorizationRequest,
    FakeAuthorizationSession,
    FakeClientCredentials,
    FakeGovBrProvider,
    FakeOAuthError,
    FakeTokenRequest,
    FakeTokenResponse,
)

_AUTHORIZATION_FIELDS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "nonce",
    "code_challenge",
    "code_challenge_method",
)
_TOKEN_FIELDS = ("grant_type", "code", "redirect_uri", "code_verifier")
_AUTHORIZATION_REQUEST_INVALID = "The authorization request is invalid."
_CLIENT_INVALID = "Client authentication failed."
_TOKEN_INVALID = "The access token is invalid or expired."


class FakeHttpRuntime(Protocol):
    """Expose only the provider fields required by the HTTP use cases."""

    provider: FakeGovBrProvider
    credential_authenticator: FakeCredentialAuthenticator | None
    prefix: str


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Return the session or immediate redirect produced by authorization."""

    session: FakeAuthorizationSession
    redirect: FakeAuthorizationRedirect | None


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Return a login result without selecting a framework response type."""

    session: FakeAuthorizationSession
    redirect: FakeAuthorizationRedirect | None
    invalid_credentials: bool = False


class FakeGovHttpApplication:
    """Coordinate FakeGov HTTP use cases without framework dependencies."""

    def __init__(
        self,
        runtime: FakeHttpRuntime,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._provider = runtime.provider
        self._credential_authenticator = runtime.credential_authenticator
        self._clock = clock

    def authorize(
        self,
        values: Mapping[str, object],
        *,
        automatic_subject: str | None = None,
    ) -> AuthorizationResult:
        parsed = required_text_values(values, _AUTHORIZATION_FIELDS)
        if parsed is None:
            raise FakeOAuthError(
                error="invalid_request",
                description=_AUTHORIZATION_REQUEST_INVALID,
            )
        session = self._provider.begin_authorization(
            FakeAuthorizationRequest(**parsed),
            now=self._clock(),
        )
        redirect = None
        if automatic_subject is not None:
            redirect = self._provider.complete_authorization(
                session=session,
                subject=automatic_subject,
                now=self._clock(),
            )
        return AuthorizationResult(session=session, redirect=redirect)

    def login(self, values: Mapping[str, object]) -> LoginResult:
        if self._credential_authenticator is None:
            parsed = required_text_values(values, ("request", "subject"))
            if parsed is None:
                raise FakeOAuthError(
                    error="invalid_request",
                    description=_AUTHORIZATION_REQUEST_INVALID,
                )
            subject = parsed["subject"]
            request = parsed["request"]
        else:
            parsed = required_text_values(values, ("request", "cpf", "password"))
            if parsed is None:
                raise FakeOAuthError(
                    error="invalid_request",
                    description=_AUTHORIZATION_REQUEST_INVALID,
                )
            user = self._credential_authenticator.authenticate(
                cpf=parsed["cpf"],
                password=SecretStr(parsed["password"]),
            )
            session = FakeAuthorizationSession(
                request=SecretStr(parsed["request"]),
                users=(),
            )
            if user is None:
                return LoginResult(
                    session=session,
                    redirect=None,
                    invalid_credentials=True,
                )
            subject = user.sub
            request = parsed["request"]

        session = FakeAuthorizationSession(request=SecretStr(request), users=())
        redirect = self._provider.complete_authorization(
            session=session,
            subject=subject,
            now=self._clock(),
        )
        return LoginResult(session=session, redirect=redirect)

    def token(
        self,
        credentials: FakeClientCredentials,
        values: Mapping[str, object],
    ) -> FakeTokenResponse:
        parsed = required_text_values(values, _TOKEN_FIELDS)
        if parsed is None:
            raise FakeOAuthError(
                error="invalid_request",
                description=_AUTHORIZATION_REQUEST_INVALID,
            )
        return self._provider.exchange_code(
            credentials=credentials,
            request=FakeTokenRequest(
                grant_type=parsed["grant_type"],
                code=SecretStr(parsed["code"]),
                redirect_uri=parsed["redirect_uri"],
                code_verifier=SecretStr(parsed["code_verifier"]),
            ),
            now=self._clock(),
        )

    def jwks(self) -> Mapping[str, object]:
        return self._provider.jwks()

    def userinfo(self, authorization: str | None) -> FakeUser:
        access_token = parse_bearer_authorization(authorization)
        if access_token is None:
            raise FakeOAuthError(error="invalid_token", description=_TOKEN_INVALID)
        return self._provider.userinfo(access_token, now=self._clock())

    @staticmethod
    def parse_client_credentials(value: str | None) -> FakeClientCredentials:
        credentials = parse_basic_authorization(value)
        if credentials is None:
            raise FakeOAuthError(error="invalid_client", description=_CLIENT_INVALID)
        return credentials


def resolve_fake_http_application(
    runtime: FakeHttpRuntime,
    *,
    clock: Callable[[], datetime],
) -> FakeGovHttpApplication:
    """Return the runtime-owned HTTP facade when one exists."""
    application = getattr(runtime, "http_application", None)
    if application is not None:
        return cast(FakeGovHttpApplication, application)
    return FakeGovHttpApplication(runtime, clock=clock)
