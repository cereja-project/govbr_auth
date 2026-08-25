"""Tests for explicit runtime ownership in synchronous adapters."""

class RuntimeStub:
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


def test_owned_runtime_closes_once() -> None:
    from govbr_auth.adapters._lifecycle import RuntimeOwner

    runtime = RuntimeStub()
    owner = RuntimeOwner(runtime=runtime, owns_runtime=True)

    owner.close()
    owner.close()

    assert runtime.close_calls == 1


def test_borrowed_runtime_is_not_closed_by_adapter() -> None:
    from govbr_auth.adapters._lifecycle import RuntimeOwner

    runtime = RuntimeStub()
    owner = RuntimeOwner(runtime=runtime, owns_runtime=False)

    owner.close()

    assert runtime.close_calls == 0


def test_async_close_closes_owned_runtime_once() -> None:
    import asyncio

    from govbr_auth.adapters._lifecycle import RuntimeOwner

    runtime = RuntimeStub()
    owner = RuntimeOwner(runtime=runtime, owns_runtime=True)

    asyncio.run(owner.aclose())
    asyncio.run(owner.aclose())

    assert runtime.close_calls == 1
