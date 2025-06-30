from __future__ import annotations
from pathlib import PurePosixPath as Path

from dataclasses import dataclass
from typing import cast

from typing_extensions import (
    Any,
    Callable,
    Coroutine,
    Generic,
    Protocol,
    TypeAlias,
    TypeVar,
    overload,
)


AnyController = TypeVar(
    "AnyController",
    bound="BaseController | AsyncControllerProtocol",
    covariant=True,
)

_T = TypeVar("_T")


class AsyncControllerProtocol(Protocol):
    async def get_state(
        self,
        path: Path | str,
        default: Any | None = None,
        write_default: bool = False,
    ) -> Any: ...

    async def set_state(
        self,
        path: Path | str,
        value: Any | None,
        eq_func: Callable[[Any | None, Any | None], bool] | None = None,
        default: Any | None = None,
        payload: Any = None,
    ) -> bool: ...

    async def del_state(
        self,
        path: Path | str,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> bool: ...


@dataclass
class StateEvent(Generic[AnyController]):
    controller: AnyController
    emitting_path: Path
    current_path: Path
    prev_value: Any | None
    new_value: Any | None
    bubbling: bool = True
    tracker: StateTracker[BaseController] | None = None
    payload: Any = None

    def get_bubbled(self) -> StateEvent[AnyController]:
        return StateEvent(
            controller=self.controller,
            emitting_path=self.emitting_path,
            current_path=self.emitting_path.parent,
            prev_value=self.prev_value,
            new_value=self.new_value,
            bubbling=self.bubbling,
            tracker=self.tracker,
        )

    @overload
    def get_state(
        self: StateEvent[AsyncControllerProtocol],
        path: Path | str,
        default: _T = None,
        write_default: bool = False,
    ) -> Coroutine[Any, Any, Any | _T]: ...

    @overload
    def get_state(
        self: StateEvent[AnyController],
        path: Path | str,
        default: Any | _T = None,
        write_default: bool = False,
    ) -> Any | _T: ...

    def get_state(
        self,
        path: Path | str,
        default: Any | None = None,
        write_default: bool = False,
    ):
        if self.tracker:
            return self.tracker.get_state(path, default, write_default)

        return self.controller.get_state(path, default, write_default)

    @overload
    def set_state(
        self: StateEvent[AsyncControllerProtocol],
        path: Path | str,
        value: Any | None,
        eq_func: Callable[[Any | None, Any | None], bool] | None = None,
        default: Any | None = None,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> Coroutine[Any, Any, bool]: ...

    @overload
    def set_state(
        self: StateEvent[AnyController],
        path: Path | str,
        value: Any | None,
        eq_func: Callable[[Any | None, Any | None], bool] | None = None,
        default: Any | None = None,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> bool: ...

    def set_state(
        self,
        path: Path | str,
        value: Any | None,
        eq_func: Callable[[Any | None, Any | None], bool] | None = None,
        default: Any | None = None,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> Coroutine[Any, Any, bool] | bool:
        return cast(
            Any,
            self.controller.set_state(
                path=path,
                value=value,
                eq_func=eq_func,
                default=default,
                payload=payload,
            ),
        )

    @overload
    def del_state(
        self: StateEvent[AsyncControllerProtocol],
        path: Path | str,
        payload: Any,
        skip_notify: bool = False,
    ) -> Coroutine[Any, Any, bool]: ...

    @overload
    def del_state(
        self: StateEvent[AnyController],
        path: Path | str,
        payload: Any,
        skip_notify: bool = False,
    ) -> bool: ...

    def del_state(
        self,
        path: Path | str,
        payload: Any,
        skip_notify: bool = False,
    ):
        return self.controller.del_state(
            path,
            payload,
            skip_notify,
        )


SyncCallback = Callable[[StateEvent[AnyController]], Any]
AsyncCallback = Callable[[StateEvent[AnyController]], Coroutine[Any, Any, Any]]


StateCallback: TypeAlias = SyncCallback[AnyController] | AsyncCallback[AnyController]


from .tracker import StateTracker  # noqa: E402
from .base import BaseController  # noqa: E402
