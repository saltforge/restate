from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath
from typing_extensions import Literal, TypeAlias
from restate.shared.caller import FunctionAdapter
from restate.shared.sentinel import Sentinel


CallbackID: TypeAlias = str | Sentinel


def is_glob_path(path: PurePosixPath) -> bool:
    for part in path.parts:
        if part == "*":
            return True

    return False


class CallbackStore:
    def __init__(self, asyncify_strategy: Literal["thread", "none"] = "none"):
        self.subscriptions: dict[PurePosixPath, set[CallbackID]] = {}
        self.callbacks: dict[CallbackID, StateCallback] = {}
        self.reverse_subscriptions: dict[CallbackID, set[PurePosixPath]] = {}
        self.asyncify_strategy = asyncify_strategy
        self.glob_paths: set[PurePosixPath] = set()

    def get_id(self, callback_or_id: CallbackID | StateCallback) -> CallbackID:
        if isinstance(callback_or_id, (str, Sentinel)):
            return callback_or_id

        return f"#{id(callback_or_id):02x}"

    def add_callback(
        self,
        callback: StateCallback,
        force_id: CallbackID | None = None,
        replace: bool = False,
    ) -> CallbackID:
        callback_id = self.get_id(force_id or callback)

        while True:  # single-iteration loop to do breaks
            if callback_id in self.callbacks:
                if callback == self.callbacks[callback_id]:
                    return callback_id

                if not replace:
                    raise ValueError(
                        f"Cannot add callback '{callback_id}': another with the same id already exists. If you want to replace state, pass replace=True to store.add_callback"
                    )

            break

        self.callbacks[callback_id] = callback

        return callback_id

    def get_matching_paths(self, path: PurePosixPath) -> Iterable[PurePosixPath]:
        if path in self.subscriptions:
            yield path

        parts = path.parts

        target_len = len(parts)

        for glob_path in self.glob_paths:
            if len(glob_path.parts) != target_len:
                continue

            for i, part in enumerate(glob_path.parts):
                if part == "*":
                    continue

                if parts[i] != part:
                    break

            else:
                yield glob_path

    def get_callbacks(self, path: PurePosixPath) -> Iterable[CallbackID]:
        for matching_path in self.get_matching_paths(path):
            for callback_id in list(self.subscriptions.get(matching_path, [])):
                yield callback_id

    def subscribe(
        self,
        path: PurePosixPath,
        callback_id: CallbackID,
        ignore_missing: bool = False,
    ):
        if is_glob_path(path):
            self.glob_paths.add(path)

        if callback_id not in self.callbacks and not ignore_missing:
            raise ValueError(
                "CallbackStore.subscribe received an unknown callback_id. If you intend to add the callback later, pass ignore_missing=True"
            )

        if path not in self.subscriptions:
            self.subscriptions[path] = set()

        if callback_id not in self.reverse_subscriptions:
            self.reverse_subscriptions[callback_id] = set()

        self.subscriptions[path].add(callback_id)
        self.reverse_subscriptions[callback_id].add(path)

    def unsubscribe(self, path: PurePosixPath, callback_id: CallbackID):
        if path not in self.subscriptions:
            return

        if callback_id not in self.subscriptions:
            return

        sub_set = self.subscriptions[path]

        if callback_id in sub_set:
            sub_set.remove(callback_id)

        if not sub_set:
            self.subscriptions.pop(path)

        rev_sub_set = self.reverse_subscriptions[callback_id]

        if path in rev_sub_set:
            rev_sub_set.remove(path)

        if not rev_sub_set:
            if is_glob_path(path):
                self.glob_paths.remove(path)

            self.reverse_subscriptions.pop(callback_id)

    def remove_callback(
        self,
        callback_id: CallbackID,
    ) -> StateCallback | None:
        rev_subs = self.reverse_subscriptions.pop(callback_id, ())

        for path in rev_subs:
            self.unsubscribe(path, callback_id)

        return self.callbacks.pop(callback_id, None)

    async def call_async(
        self,
        callback_id: CallbackID,
        event: StateEvent,
    ):
        callback = self.callbacks.get(callback_id)

        if callback is None:
            return

        adapted = FunctionAdapter(callback)  # type: ignore because Pyright is mad, 'function is not assignable to AnyFunction'
        await adapted.call_async(event)

    def call_sync(
        self,
        callback_id: CallbackID,
        event: StateEvent,
    ):
        callback = self.callbacks.get(callback_id)

        if callback is None:
            return

        # TODO: raise an issue in Pyright
        adapted = FunctionAdapter(callback)  # type: ignore because Pyright is mad, 'function is not assignable to AnyFunction'
        adapted.call_sync(event)


from .internal_types import StateCallback, StateEvent  # noqa: E402
