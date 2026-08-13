"""FastAPI-only public interface for asynchronous Gov.br authentication."""

from govbr_auth.fastapi import (
    AuthContext,
    AuthSuccessHandler,
    GovBrAuth,
    create_govbr_router,
)
from govbr_auth.core.transactions import generate_transaction_secret

__all__ = (
    "AuthContext",
    "AuthSuccessHandler",
    "GovBrAuth",
    "create_govbr_router",
    "generate_transaction_secret",
)

VERSION = "1.0.0rc1"
__version__ = "1.0.0rc1"
