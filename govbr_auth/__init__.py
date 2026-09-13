"""Framework-neutral public helpers for Gov.br authentication."""

from govbr_auth.core.transactions import generate_transaction_secret

__all__ = ("generate_transaction_secret",)

VERSION = "1.0.1"
__version__ = VERSION
