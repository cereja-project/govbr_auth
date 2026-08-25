"""Explicit ownership for runtimes created by synchronous adapters."""

from dataclasses import dataclass
from typing import Protocol

from govbr_auth.adapters._sync import run_sync


class _ClosableRuntime(Protocol):
    async def aclose(self) -> None: ...


@dataclass(slots=True)
class RuntimeOwner:
    """Close an adapter-created runtime without closing borrowed runtimes."""

    runtime: _ClosableRuntime
    owns_runtime: bool
    _closed: bool = False

    def close(self) -> None:
        """Close an owned runtime exactly once."""
        if self._closed:
            return
        run_sync(self.aclose)

    async def aclose(self) -> None:
        """Close an owned runtime from an async framework lifecycle."""
        if self._closed:
            return
        self._closed = True
        if self.owns_runtime:
            await self.runtime.aclose()
