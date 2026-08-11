"""Public APIs for legacy adapters and the experimental strict OAuth core."""

from govbr_auth.core.authorization import AuthorizationBuilder, AuthorizationRequest
from govbr_auth.core.client import AuthenticationResult, GovBrClient
from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.errors import (
    ExpiredTransactionError,
    GovBrAuthError,
    InvalidIdTokenError,
    InvalidStateError,
)
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration
from govbr_auth.core.models import AuthTransaction, GovBrAddress, GovBrUser, TokenSet
from govbr_auth.core.settings import GovBrSettings, ProviderEnvironment
from govbr_auth.core.token_validation import IdTokenValidator
from govbr_auth.core.transactions import InMemoryTransactionStore, TransactionStore

__all__ = [
    "AuthenticationResult",
    "AuthTransaction",
    "AuthorizationBuilder",
    "AuthorizationRequest",
    "ExpiredTransactionError",
    "GovBrAddress",
    "GovBrAuthError",
    "GovBrAuthorize",
    "GovBrClient",
    "GovBrConfig",
    "GovBrIntegration",
    "GovBrSettings",
    "GovBrUser",
    "IdTokenValidator",
    "InMemoryTransactionStore",
    "InvalidIdTokenError",
    "InvalidStateError",
    "ProviderEnvironment",
    "TokenSet",
    "TransactionStore",
]
