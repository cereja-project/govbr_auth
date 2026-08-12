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
from govbr_auth.fastapi import (
    AuthContext,
    AuthSuccessHandler,
    GovBrAuth,
    create_govbr_router,
)

__all__ = [
    "AuthenticationResult",
    "AuthContext",
    "AuthSuccessHandler",
    "AuthTransaction",
    "AuthorizationBuilder",
    "AuthorizationRequest",
    "ExpiredTransactionError",
    "GovBrAddress",
    "GovBrAuthError",
    "GovBrAuthorize",
    "GovBrAuth",
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
    "create_govbr_router",
]
