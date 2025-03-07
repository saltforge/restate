from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from time import perf_counter
from typing_extensions import Any, Generic, TypeVar


AnyController = TypeVar(
    "AnyController",
    bound="BaseController",
    covariant=True,
)


@dataclass
class StateTracker(Generic[AnyController]):
    controller: AnyController
    run_start: float = -1
    run_end: float = -1
    _used_paths: set[PurePosixPath] | None = None

    @property
    def paths(self):
        if self._used_paths is None:
            self._used_paths = set()

        return self._used_paths

    def start(self):
        self.run_start = perf_counter()

    def stop(self):
        self.run_end = perf_counter()

    def track(self, path: PurePosixPath):
        self.paths.add(path)

    def get_state(
        self,
        path: PurePosixPath | str,
        default: Any | None = None,
        write_default: bool = False,
    ):
        self.track(self.controller.resolve_path(path))
        return self.controller.get_state(path, default, write_default)


class StateTrackerController(Generic[AnyController]):
    def __init__(
        self, state_controller: AnyController, callback: StateCallback[AnyController]
    ):
        self.last_run: StateTracker | None = None
        self.callback = callback
        self.state_controller = state_controller

    def create_tracker(self):
        return StateTracker(self.state_controller)

    def reconcile(
        self,
        old_run: StateTracker[AnyController] | None,
        new_run: StateTracker[AnyController],
    ):
        if old_run is None:
            old_paths = set()
        else:
            old_paths = old_run.paths

        new_paths = new_run.paths

        for path in old_paths | new_paths:
            if path not in new_paths:
                self.state_controller.unsubscribe(path, self.callback)

            if path not in old_paths:
                self.state_controller.subscribe(path, self.callback)

    def submit_tracker(
        self,
        run: StateTracker[AnyController],
    ):
        if self.last_run:
            if self.last_run.run_end > run.run_end:
                return

        self.reconcile(self.last_run, run)

        self.last_run = run


from .internal_types import StateCallback  # noqa: E402
from .base import BaseController  # noqa: E402
