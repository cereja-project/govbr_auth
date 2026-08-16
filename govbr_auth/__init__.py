"""FastAPI-only public interface for asynchronous Gov.br authentication."""

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


def __getattr__(name: str) -> object:
    """Load FastAPI public objects only when callers request them."""
    if name not in {
        "AuthContext",
        "AuthSuccessHandler",
        "GovBrAuth",
        "create_govbr_router",
    }:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from govbr_auth.fastapi import (
        AuthContext,
        AuthSuccessHandler,
        GovBrAuth,
        create_govbr_router,
    )

    exports = {
        "AuthContext": AuthContext,
        "AuthSuccessHandler": AuthSuccessHandler,
        "GovBrAuth": GovBrAuth,
        "create_govbr_router": create_govbr_router,
    }
    value = exports[name]
    globals()[name] = value
    return value
