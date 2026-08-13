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

VERSION = "0.2.2.final.0"
__version__ = "0.2.2"
