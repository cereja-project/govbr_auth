"""Short-lived, authenticated browser proofs for OAuth callback correlation."""

import hashlib
import secrets
from collections.abc import Mapping, MutableMapping
from datetime import datetime
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from govbr_auth.core.errors import ExpiredTransactionError, InvalidStateError
from govbr_auth.core.settings import GovBrSettings

_MAX_AGE = 300
_MAX_PENDING = 8
_PURPOSE = b"govbr-auth/browser-binding/v1:"


class _CookieResponse(Protocol):
    headers: MutableMapping[str, str]

    def set_cookie(self, key: str, value: str = "", **kwargs: object) -> None: ...


class BrowserBinding:
    """Bind a protected OAuth state to an independent, host-only browser cookie.

    The proof is encrypted/authenticated separately from state and is never sent
    to the provider. A state alone cannot be used to forge its browser proof.
    Distinct cookie names preserve simultaneous login attempts in separate tabs.
    """

    def __init__(self, settings: GovBrSettings) -> None:
        self._fernet = Fernet(
            settings.transaction_secret.get_secret_value().encode("ascii")
        )
        self._secure = settings.redirect_uri.scheme == "https"
        scope = f"{settings.client_id}\0{settings.redirect_uri}"
        self._scope = self._digest(scope)
        prefix = "__Host-govbr-auth-" if self._secure else "govbr-auth-local-"
        self._prefix = prefix + self._scope.hex()[:16] + "-"

    def cookie_name(self, state: str) -> str:
        """Select only this transaction's cookie, without putting state in its name."""
        return self._prefix + self._digest(state).hex()

    def start(
        self,
        response: _CookieResponse,
        state: str,
        *,
        now: datetime,
        cookies: Mapping[str, str],
    ) -> None:
        """Set a fresh browser-only proof when issuing the authorization redirect."""
        pending = [name for name in cookies if name.startswith(self._prefix)]
        for name in pending[: max(0, len(pending) - _MAX_PENDING + 1)]:
            self._set_cookie(response, name, "", max_age=0)
        proof = self._fernet.encrypt_at_time(
            _PURPOSE + self._scope + self._digest(state),
            current_time=int(now.timestamp()),
        ).decode("ascii")
        self._set_cookie(response, self.cookie_name(state), proof, max_age=_MAX_AGE)
        self._no_store(response)

    def validate(
        self, state: str, cookies: Mapping[str, str], *, now: datetime
    ) -> None:
        """Reject a missing, expired, forged or unrelated proof before provider I/O."""
        value = cookies.get(self.cookie_name(state), "")
        payload = None
        try:
            payload = self._fernet.decrypt(value.encode("ascii"))
        except (InvalidToken, UnicodeEncodeError):
            pass
        if payload is None or not secrets.compare_digest(
            payload, _PURPOSE + self._scope + self._digest(state)
        ):
            raise InvalidStateError("OAuth browser binding is invalid")
        issued_at = self._fernet.extract_timestamp(value.encode("ascii"))
        current_time = int(now.timestamp())
        if current_time < issued_at:
            raise InvalidStateError("OAuth browser binding is invalid")
        if current_time >= issued_at + _MAX_AGE:
            raise ExpiredTransactionError("OAuth browser binding has expired")

    def finish(self, response: _CookieResponse, state: str | None) -> None:
        """Remove this transaction's proof on success or failure; retain other tabs."""
        if state:
            self._set_cookie(response, self.cookie_name(state), "", max_age=0)
        self._no_store(response)

    def _set_cookie(
        self, response: _CookieResponse, name: str, value: str, *, max_age: int
    ) -> None:
        response.set_cookie(
            name,
            value,
            max_age=max_age,
            path="/",
            secure=self._secure,
            httponly=True,
            samesite="none" if self._secure else "lax",
        )

    @staticmethod
    def _digest(state: str) -> bytes:
        return hashlib.sha256(state.encode("utf-8", errors="surrogatepass")).digest()

    @staticmethod
    def _no_store(response: _CookieResponse) -> None:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
