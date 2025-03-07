from __future__ import annotations

from pathlib import PurePosixPath as Path
from typing import Callable
from typing_extensions import Any, Awaitable, Self, Sequence, TypeVar
import operator

from .base import BaseController, DeriveData

from restate.shared.constants import ROOT_PATH
from restate.backends.asyncify import AsyncifyBackend
from restate.backends.base import AsyncBackend, Backend
from restate.backends.memory import InMemoryBackend
from restate.shared.sentinel import Sentinel

_T = TypeVar("_T")


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
        path: Path | str,
        default: _T = None,
        write_default: bool = False,
    ) -> Any | _T:
        """
        Read the state at the `path`

        Pass `default` as a value to return if state doesn't exist at `path`.
        Pass `write_default=True` to write `default` value if state doesn't exist at `path`.
        """
        fake_default = Sentinel("state_default")

        value = await self.backend.read(self.resolve_path(path), fake_default)

        if isinstance(value, Sentinel):
            if write_default:
                await self.write_state(path, default)

            return default

        return value

    async def write_state(
        self,
        path: Path | str,
        value: Any | None,
    ):
        await self.backend.write(self.resolve_path(path), value)

    async def notify(
        self,
        path: Path | str,
        event: StateEvent[Self],
    ):
        path = self.resolve_path(path)

        for callback_id in self.callbacks.get_callbacks(path):
            # if event is bubbling, notify every caller
            # otherwise notify only special-cased callers
            if event.bubbling or isinstance(callback_id, Sentinel):
                await self.callbacks.call_async(callback_id, event)

        if path != ROOT_PATH:
            await self.notify(path.parent, event.get_bubbled())

    async def set_state(
        self,
        path: Path | str,
        value: Any | None,
        eq_func: Callable[[Any | None, Any | None], bool] | None = None,
        default: Any | None = None,
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

        event = self.build_event(path, prev_value, value)

        await self.write_state(path, value)
        await self.notify(path, event)

        return True

    async def ping(self, path: Path | str, default: Any | None = None):
        """
        Notifies path subscribers unconditionally.
        default is passed to .get_state
        """

        value = await self.get_state(path, default)

        await self.notify(path, self.build_event(path, value, value))

    async def derive_many(
        self,
        dest: Path | str,
        sources: Sequence[Path | str],
        transform: Callable[
            [DeriveData],
            Awaitable[Any | None],
        ],
    ):
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
            )

        callback_id = Sentinel(f"derive:{dest}")
        self.callbacks.remove_callback(callback_id)
        self.register_callback(callback, force_id=callback_id)

        for p in sources:
            self.subscribe_by_id(
                p,
                callback_id,
            )

        await callback(self.build_event(ROOT_PATH, None, None))

    async def derive(
        self,
        dest: Path | str,
        source: Path | str,
        transform: Callable[[Any | None], Awaitable[Any | None]],
    ):
        def full_transform(d: DeriveData) -> Awaitable[Any | None]:
            return transform(d.get(source))

        await self.derive_many(
            dest,
            [source],
            transform=full_transform,
        )

    async def track(self, callback: StateCallback[Self]):
        callback_id = self.register_callback(callback)

        async def wrapped_callback(event: StateEvent[Self]):
            tracker = tracker_controller.create_tracker()
            event.tracker = tracker
            await self.callbacks.call_async(callback_id, event)
            event.tracker = None
            tracker_controller.submit_tracker(tracker)

        wrapped_id = self.register_callback(wrapped_callback)

        tracker_controller = StateTrackerController(self, wrapped_callback)

        await self.callbacks.call_async(
            wrapped_id,
            self.build_event(ROOT_PATH, prev_value=None, new_value=None),
        )


from .internal_types import StateEvent, StateCallback  # noqa: E402
from .tracker import StateTrackerController  # noqa: E402
