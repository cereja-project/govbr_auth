"""Check loop identity, context isolation and shutdown for WSGI callers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

import pytest

from govbr_auth.adapters import _sync


def test_wsgi_calls_share_one_loop_and_preserve_independent_request_contexts():
    request_id = ContextVar("request_id")

    async def inspect():
        initial = request_id.get()
        await asyncio.sleep(0.01)
        assert request_id.get() == initial
        return initial, id(asyncio.get_running_loop())

    def request(value):
        token = request_id.set(value)
        try:
            return _sync.run_sync(inspect)
        finally:
            request_id.reset(token)

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(request, range(16)))
    assert [result[0] for result in results] == list(range(16))
    assert len({result[1] for result in results}) == 1


def test_factory_exception_does_not_break_following_calls():
    async def fail():
        raise ValueError("expected failure")

    with pytest.raises(ValueError, match="expected failure"):
        _sync.run_sync(fail)
    assert _sync.run_sync(lambda: asyncio.sleep(0, result="alive")) == "alive"


def test_shutdown_is_idempotent_and_new_calls_get_a_fresh_loop():
    async def loop():
        return asyncio.get_running_loop()

    first = _sync.run_sync(loop)
    runner = _sync._get_runner()
    _sync._shutdown_runner()
    _sync._shutdown_runner()
    assert first.is_closed()
    assert not runner.thread.is_alive()
    second = _sync.run_sync(loop)
    assert second is not first
    assert not second.is_closed()


def test_child_pid_does_not_stop_parent_runner_and_reinitializes_its_state(monkeypatch):
    parent = _sync._get_runner()
    parent_pid = _sync._runner_pid
    # Model an inherited reference without ever closing the parent's event loop.
    with monkeypatch.context() as patch:
        patch.setattr(_sync.os, "getpid", lambda: parent_pid + 1)
        _sync._shutdown_runner()
        assert _sync._runner is parent
        child = _sync._get_runner()
        assert child is not parent
        assert _sync._runner_pid == parent_pid + 1
        _sync._shutdown_runner()
    parent.close()
    _sync._get_runner()
    assert _sync._runner_pid == parent_pid


def test_thread_start_failure_closes_allocated_loop(monkeypatch):
    loop = asyncio.new_event_loop()

    def fail_start(self):
        raise RuntimeError("cannot start thread")

    monkeypatch.setattr(_sync.asyncio, "new_event_loop", lambda: loop)
    monkeypatch.setattr(_sync.threading.Thread, "start", fail_start)
    with pytest.raises(RuntimeError, match="cannot start thread"):
        _sync._LoopRunner()
    assert loop.is_closed()
