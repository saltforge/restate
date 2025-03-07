from __future__ import annotations

import asyncio
from asyncio.protocols import Protocol
from typing_extensions import Coroutine, Generic, ParamSpec, TypeIs, TypeVar


_P = ParamSpec("_P")
_R = TypeVar("_R")


class SyncFunction(Protocol, Generic[_P, _R]):
    def __call__(self, *args: _P.args, **kwds: _P.kwargs) -> _R: ...


class AsyncFunction(Protocol, Generic[_P, _R]):
    def __call__(
        self, *args: _P.args, **kwds: _P.kwargs
    ) -> Coroutine[None, None, _R]: ...


AnyFunction = SyncFunction[_P, _R] | AsyncFunction[_P, _R]


def is_awaitable(
    cb: _R | Coroutine[None, None, _R],
) -> TypeIs[Coroutine[None, None, _R]]:
    return asyncio.iscoroutine(cb)


class FunctionAdapter(Generic[_P, _R]):
    def __init__(
        self,
        func: AnyFunction[_P, _R],
    ):
        self.func = func

    async def call_async(
        self,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        maybe_coro = self.func(*args, **kwargs)

        if is_awaitable(maybe_coro):
            return await maybe_coro

        return maybe_coro

    def call_sync(
        self,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        maybe_coro = self.func(*args, **kwargs)

        if is_awaitable(maybe_coro):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(maybe_coro)

        return maybe_coro
