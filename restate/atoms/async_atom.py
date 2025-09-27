from __future__ import annotations
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar


from restate.controllers.callback_store import CallbackID
from restate.controllers.internal_types import (
    EqualityFunction,
    PathLike,
    StateCallback,
)

if TYPE_CHECKING:
    from restate.controllers import ControllerAsync
    from restate.controllers.base import DeriveData

from .core import BaseAtom

_T = TypeVar("_T")
_R = TypeVar("_R")


class AsyncAtom(BaseAtom[_T]):
    def __init__(
        self,
        controller: ControllerAsync,
        path: PathLike,
        default: _T = None,
    ) -> None:
        self.default = default
        self.controller = controller
        self.path = path

    async def set(
        self,
        value: _T,
        eq_func: EqualityFunction | None = None,
        payload: Any = None,
        skip_notify: bool = False,
    ):
        await self.controller.set_state(
            self.path,
            value,
            eq_func=eq_func,
            default=self.default,
            payload=payload,
            skip_notify=skip_notify,
        )

    async def get(self, write_default: bool = False) -> _T:
        return await self.controller.get_state(
            self.path,
            default=self.default,
            write_default=write_default,
        )

    def subscribe_by_id(
        self,
        callback_id: CallbackID,
        ignore_missing: bool = False,
    ) -> CallbackID:
        return self.controller.subscribe_by_id(
            self.path,
            callback_id,
            ignore_missing=ignore_missing,
        )

    def subscribe(
        self,
        callback: StateCallback[ControllerAsync, _T],
        force_id: CallbackID | None = None,
        replace: bool = False,
    ) -> CallbackID:
        return self.controller.subscribe(
            self.path,
            callback,
            force_id=force_id,
            replace=replace,
        )

    async def derive(
        self,
        dest: PathLike | BaseAtom[_R],
        transform: Callable[[_T], Awaitable[_R]],
    ):
        return await self.controller.derive(
            dest=dest,
            source=self.path,
            transform=transform,  # type: ignore (atom default)
        )

    async def ping(
        self,
        payload: Any = None,
    ):
        await self.controller.ping(
            self.path,
            self.default,
            payload,
        )

    async def derive_from(
        self,
        *sources: PathLike,
        transform: Callable[[DeriveData], Awaitable[_T]],
        payload: Any = None,
    ):
        await self.controller.derive_many(
            self.path,
            sources,
            transform,
            payload=payload,
        )
