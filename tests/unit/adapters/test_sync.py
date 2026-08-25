"""Tests for the synchronous framework-adapter bridge."""

import asyncio

import pytest


def test_run_sync_executes_an_async_factory_from_wsgi_code() -> None:
    from govbr_auth.adapters._sync import run_sync

    async def operation() -> str:
        return "complete"

    assert run_sync(operation) == "complete"


def test_run_sync_fails_closed_inside_an_active_event_loop() -> None:
    from govbr_auth.adapters._sync import run_sync

    async def operation() -> str:
        return "complete"

    async def caller() -> None:
        with pytest.raises(RuntimeError, match="event loop"):
            run_sync(operation)

    asyncio.run(caller())

