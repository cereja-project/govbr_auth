"""FastAPI-only public interface for asynchronous Gov.br authentication."""

from govbr_auth.fastapi import (
    AuthContext,
    AuthSuccessHandler,
    GovBrAuth,
    create_govbr_router,
)

__all__ = (
    "AuthContext",
    "AuthSuccessHandler",
    "GovBrAuth",
    "create_govbr_router",
)

VERSION = "0.2.2.final.0"
__version__ = "0.2.2"
