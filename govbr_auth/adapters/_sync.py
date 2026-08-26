"""Explicit synchronous execution for adapters with WSGI handlers."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from asgiref.sync import async_to_sync

T = TypeVar("T")


def run_sync(factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async factory from synchronous framework code.

    ``async_to_sync`` refuses calls from the same thread as an active event
    loop, which prevents a synchronous adapter from silently blocking it.
    """
    return async_to_sync(factory)()
