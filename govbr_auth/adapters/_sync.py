"""Process-local asynchronous execution for synchronous framework adapters."""

import asyncio
import atexit
import os
import threading
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class _LoopRunner:
    """Keep pooled HTTP I/O and shutdown on the same loop across WSGI requests."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._serve, name="govbr-auth-async", daemon=True
        )
        try:
            self.thread.start()
        except RuntimeError:
            self.loop.close()
            raise

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        with asyncio.Runner(loop_factory=lambda: self.loop):
            self.loop.run_forever()

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


_runner: _LoopRunner | None = None
_runner_lock = threading.Lock()
_runner_pid = os.getpid()


def _get_runner() -> _LoopRunner:
    global _runner, _runner_lock, _runner_pid
    pid = os.getpid()
    if pid != _runner_pid:
        # A prefork worker cannot use the parent's loop, thread or mutex.
        _runner, _runner_lock, _runner_pid = None, threading.Lock(), pid
    with _runner_lock:
        if _runner is None:
            _runner = _LoopRunner()
        return _runner


def _shutdown_runner() -> None:
    global _runner
    if os.getpid() != _runner_pid:
        return
    with _runner_lock:
        if _runner is not None:
            _runner.close()
            _runner = None


def run_sync(factory: Callable[[], Awaitable[T]]) -> T:
    """Run on one process-local loop while retaining the caller's context.

    Refuse calls from an active event loop. Owned runtimes must be closed with
    the adapter's close(); borrowed WSGI runtimes use run_sync(runtime.aclose).
    Do not share a live runtime with an unrelated ASGI loop or across a fork.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("run_sync cannot run in a thread with an active event loop")

    async def invoke() -> T:
        return await factory()

    loop = _get_runner().loop
    future = asyncio.run_coroutine_threadsafe(invoke(), loop)
    try:
        return future.result()
    except BaseException:
        future.cancel()
        raise


atexit.register(_shutdown_runner)
