"""Construct Gov.br OAuth authorization requests with PKCE binding."""

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from govbr_auth.core.settings import GovBrSettings
from govbr_auth.core.transactions import TransactionCodec


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Represent the redirect URL and opaque state of an OAuth authorization request."""

    url: str
    state: str


class AuthorizationBuilder:
    """Build Gov.br OAuth authorization requests bound to protected transactions."""

    def __init__(self, settings: GovBrSettings, transactions: TransactionCodec) -> None:
        """Store the validated provider configuration and transaction collaborator."""
        self._settings = settings
        self._transactions = transactions

    def build(self, *, now: datetime) -> AuthorizationRequest:
        """Create a transaction and encode its nonce and PKCE challenge in the redirect URL."""
        state, transaction = self._transactions.issue(now=now)
        verifier = transaction.code_verifier.get_secret_value().encode("ascii")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier).digest())
        code_challenge = challenge.rstrip(b"=").decode("ascii")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.client_id,
                "scope": self._settings.scope,
                "redirect_uri": str(self._settings.redirect_uri),
                "nonce": transaction.nonce.get_secret_value(),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return AuthorizationRequest(
            url=f"{self._settings.authorization_url}?{query}",
            state=state,
        )

    def build_logout(self) -> str:
        """Build the provider logout URL from the configured fixed return URI."""
        logout_url = self._settings.logout_url
        post_logout_redirect_uri = self._settings.post_logout_redirect_uri
        if logout_url is None or post_logout_redirect_uri is None:
            raise ValueError(
                "logout_url and post_logout_redirect_uri must be configured together"
            )
        query = urlencode({"post_logout_redirect_uri": str(post_logout_redirect_uri)})
        separator = "&" if "?" in str(logout_url) else "?"
        return f"{logout_url}{separator}{query}"
