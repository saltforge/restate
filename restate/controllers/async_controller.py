from __future__ import annotations

from pathlib import PurePosixPath as Path
from typing_extensions import Callable, Any, Awaitable, Self, Sequence, TypeVar
import operator

from .base import BaseAtom, BaseController, DeriveData
from .callback_store import CallbackID

from restate.shared.constants import ROOT_PATH
from restate.backends.asyncify import AsyncifyBackend
from restate.backends.base import AsyncBackend, Backend
from restate.backends.memory import InMemoryBackend
from restate.shared.sentinel import Sentinel


_T = TypeVar("_T")
_R = TypeVar("_R")


fake_default = Sentinel("state_default")


class ControllerAsync(BaseController):
    def __init__(
        self,
        backend: AsyncBackend | Backend | None = None,
    ):
        if backend is None:
            backend = InMemoryBackend()

        if not isinstance(backend, AsyncBackend):
            backend = AsyncifyBackend(backend)

        self.backend: AsyncBackend = backend

        super().__init__()

    async def get_state(
        self,
        path: PathLike,
        default: _T = None,
        write_default: bool = False,
    ) -> Any | _T:
        """
        Read the state at the `path`

        Pass `default` as a value to return if state doesn't exist at `path`.
        Pass `write_default=True` to write `default` value if state doesn't exist at `path`.
        """
        value = await self.backend.read(self.resolve_path(path), fake_default)

        if isinstance(value, Sentinel):
            if write_default:
                await self.write_state(path, default)

            return default

        return value

    async def write_state(
        self,
        path: PathLike,
        value: Any | None,
    ):
        await self.backend.write(self.resolve_path(path), value)

    async def notify(
        self,
        path: PathLike,
        event: StateEvent[Self, _T],
    ):
        path = self.resolve_path(path)

        for callback_id in self.callbacks.get_callbacks(path):
            # if event is bubbling, notify every caller
            # otherwise notify only special-cased callers
            if event.bubbling or isinstance(callback_id, Sentinel):
                await self.callbacks.call_async(callback_id, event)

        if path != ROOT_PATH:
            await self.notify(path.parent, event.get_bubbled())

    async def set_state(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        path: PathLike,
        value: Any | None,
        eq_func: EqualityFunction | None = None,
        default: Any | None = None,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> bool:
        """
        Sets the path state to the given value and notifies the subscribers.
        If value is the same as the previous one, doesn't notify or rewrite.
        The comparison behaviour is done by the given eq_func (`==` comparison by default)

        `default` is passed to get_state to retrieve the prev_value.

        If you want to notify all subscribers unconditionally, check .ping method (it skips writing and comparison)

        Returns boolean to show if a rewrite has happened.
        """

        path = self.resolve_path(path)
        prev_value = await self.get_state(path, default)

        if not eq_func:
            eq_func = operator.eq

        are_equal = bool(eq_func(value, prev_value))

        if are_equal:
            return False

        event = self.build_event(path, prev_value, value, payload)

        await self.write_state(path, value)

        if not skip_notify:
            await self.notify(path, event)

        return True

    async def del_state(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        path: PathLike,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> bool:
        path = self.resolve_path(path)
        prev_value = await self.get_state(path, fake_default)

        if prev_value == fake_default:
            return False

        event = self.build_event(path, prev_value, None, payload)

        await self.backend.delete(path)

        if not skip_notify:
            await self.notify(path, event)

        return True

    async def ping(
        self,
        path: PathLike,
        default: Any | None = None,
        payload: Any = None,
    ):
        """
        Notifies path subscribers unconditionally.
        default is passed to .get_state
        """

        value = await self.get_state(path, default)

        await self.notify(path, self.build_event(path, value, value, payload))

    async def derive_many(
        self,
        dest: PathLike,
        sources: Sequence[PathLike],
        transform: Callable[
            [DeriveData],
            Awaitable[Any | None],
        ],
        payload: Any = None,
    ) -> CallbackID:
        async def callback(event: StateEvent[Self]):
            update_data: dict[Path, Any | None] = {}

            for p in sources:
                resolved = self.resolve_path(p)

                if p == event.emitting_path:
                    update_data[resolved] = event.new_value
                else:
                    update_data[resolved] = await self.get_state(p)

            await self.set_state(
                dest,
                await transform(DeriveData(self, update_data)),
                payload=payload,
            )

        callback_id = Sentinel(f"derive:{dest}")
        self.callbacks.remove_callback(callback_id)
        self.register_callback(callback, force_id=callback_id)

        start_event = self.build_event(ROOT_PATH, None, None, payload)

        for p in sources:
            self.subscribe_by_id(
                p,
                callback_id,
            )

        await callback(start_event)

        return callback_id

    async def derive(
        self,
        dest: PathLike,
        source: PathLike,
        transform: Callable[[Any | None], Awaitable[Any | None]],
        payload: Any = None,
    ) -> CallbackID:
        def full_transform(d: DeriveData) -> Awaitable[Any | None]:
            return transform(d.get(source))

        return await self.derive_many(
            dest,
            [source],
            transform=full_transform,
            payload=payload,
        )

    async def track(self, callback: StateCallback[Self, _T], payload: Any = None):
        callback_id = self.register_callback(callback)

        async def wrapped_callback(event: StateEvent[Self, _T]):
            tracker = tracker_controller.create_tracker()
            event.tracker = tracker
            await self.callbacks.call_async(callback_id, event)
            event.tracker = None
            tracker_controller.submit_tracker(tracker)

        wrapped_id = self.register_callback(wrapped_callback)

        tracker_controller = StateTrackerController(self, wrapped_callback)

        await self.callbacks.call_async(
            wrapped_id,
            self.build_event(
                ROOT_PATH,
                prev_value=None,
                new_value=None,
                payload=payload,
            ),
        )

    def atom(self, path: PathLike, default: _T = None) -> AtomAsync[_T]:
        return AtomAsync(
            controller=self,
            path=path,
            default=default,
        )

    def named_atom(
        self,
        key: str,
        default: _T = None,
    ) -> AtomAsync[_T]:
        return AtomAsync(
            controller=self,
            path=None,
            key=key,
            default=default,
        )


class AtomAsync(BaseAtom[ControllerAsync, _T]):
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

    async def delete(
        self,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> bool:
        return await self.controller.del_state(
            self.path,
            payload=payload,
            skip_notify=skip_notify,
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
        callback: StateCallback[ControllerAsync, Any],
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
        dest: PathLike | BaseAtom[Any, _R],
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

    def on_change(self, callback: StateCallback[ControllerAsync, Any]):
        self.subscribe(callback)
        return callback


from .internal_types import EqualityFunction, PathLike, StateEvent, StateCallback  # noqa: E402
from .tracker import StateTrackerController  # noqa: E402
