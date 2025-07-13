from typing_extensions import Any, Self, Sequence, Callable, TypeVar
import operator
from pathlib import PurePosixPath as Path

from .internal_types import StateCallback, StateEvent
from .base import BaseController, DeriveData
from .callback_store import CallbackID

from restate.shared.constants import ROOT_PATH
from restate.shared.sentinel import Sentinel
from restate.backends.base import Backend
from restate.backends.memory import InMemoryBackend


_T = TypeVar("_T")


fake_default = Sentinel("state_default")


class ControllerSync(BaseController):
    def __init__(self, backend: Backend | None = None):
        if backend is None:
            backend = InMemoryBackend()

        self.backend: Backend = backend

        super().__init__()

    def get_state(
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

        value = self.backend.read(self.resolve_path(path), fake_default)

        if isinstance(value, Sentinel):
            if write_default:
                self.write_state(path, default)

            return default

        return value

    def write_state(
        self,
        path: Path | str,
        value: Any | None,
    ):
        self.backend.write(self.resolve_path(path), value)

    def notify(
        self,
        path: Path | str,
        event: StateEvent[Self],
    ):
        path = self.resolve_path(path)

        for callback_id in self.callbacks.get_callbacks(path):
            # if event is bubbling, notify every caller
            # otherwise notify only special-cased callers
            if event.bubbling or isinstance(callback_id, Sentinel):
                self.callbacks.call_sync(callback_id, event)

        if path != ROOT_PATH:
            self.notify(path.parent, event.get_bubbled())

    def set_state(
        self,
        path: Path | str,
        value: Any | None,
        eq_func: Callable[[Any | None, Any | None], bool] | None = None,
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

        Returns boolean to show if a rewrite has happened
        """

        path = self.resolve_path(path)
        prev_value = self.get_state(path, default)

        if not eq_func:
            eq_func = operator.eq

        are_equal = bool(eq_func(value, prev_value))

        if are_equal:
            return False

        event = self.build_event(path, prev_value, value, payload)

        self.write_state(path, value)

        if not skip_notify:
            self.notify(path, event)

        return True

    def del_state(
        self,
        path: Path | str,
        payload: Any = None,
        skip_notify: bool = False,
    ) -> bool:
        path = self.resolve_path(path)
        prev_value = self.get_state(path, fake_default)

        if prev_value == fake_default:
            return False

        event = self.build_event(path, prev_value, None, payload)

        self.backend.delete(path)

        if not skip_notify:
            self.notify(path, event)

        return True

    def ping(
        self,
        path: Path | str,
        default: Any | None = None,
        payload: Any = None,
    ):
        """
        Notifies path subscribers unconditionally.
        default is passed to .get_state
        """

        value = self.get_state(path, default)

        self.notify(path, self.build_event(path, value, value, payload))

    def derive_many(
        self,
        dest: Path | str,
        sources: Sequence[Path | str],
        transform: Callable[[DeriveData], Any | None],
        payload: Any = None,
    ) -> CallbackID:
        def callback(event: StateEvent):
            update_data: dict[Path, Any | None] = {}

            for p in sources:
                resolved = self.resolve_path(p)

                if resolved == event.emitting_path:
                    update_data[resolved] = event.new_value
                else:
                    update_data[resolved] = self.get_state(p)

            self.set_state(
                dest, transform(DeriveData(self, update_data)), payload=payload
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

        callback(start_event)

        return callback_id

    def derive(
        self,
        dest: Path | str,
        source: Path | str,
        transform: Callable[[Any | None], Any | None],
        payload: Any = None,
    ) -> CallbackID:
        return self.derive_many(
            dest,
            [source],
            transform=lambda d: transform(d.get(source)),
            payload=payload,
        )

    def track(self, callback: StateCallback[Self], payload: Any = None):
        callback_id = self.register_callback(callback)

        def wrapped_callback(event: StateEvent[Self]):
            tracker = tracker_controller.create_tracker()
            event.tracker = tracker
            result = self.callbacks.call_sync(callback_id, event)
            event.tracker = None
            tracker_controller.submit_tracker(tracker)
            return result

        wrapped_id = self.register_callback(wrapped_callback)

        tracker_controller = StateTrackerController(self, wrapped_callback)

        self.callbacks.call_sync(
            wrapped_id,
            self.build_event(
                ROOT_PATH,
                prev_value=None,
                new_value=None,
                payload=payload,
            ),
        )


from .tracker import StateTrackerController  # noqa: E402
