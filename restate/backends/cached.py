# restate/restate/backends/cached.py
from __future__ import annotations

import atexit
import asyncio
import time
from pathlib import PurePosixPath as Path
from typing_extensions import Any, Generic, Literal, TypeAlias, TypeVar, Union
from weakref import WeakSet

from restate.shared.sentinel import Sentinel

from .base import Backend, AsyncBackend
from .memory import InMemoryBackend


_B = TypeVar("_B", bound=Union[Backend, AsyncBackend])
_T = TypeVar("_T")

OperationType: TypeAlias = Literal["read", "write", "delete"]


class Operation:
    def __init__(self, op_type: OperationType, path: Path, value: Any | None = None):
        self.type = op_type
        self.path = path
        self.value = value
        self.timestamp = time.time()


class CachingBackendBase(Generic[_B]):
    """Base class for caching backends with common functionality"""

    # Track all instances for cleanup on exit
    _instances = WeakSet()

    def __init__(
        self,
        backend: _B,
        flush_interval: float = 5.0,  # seconds
        flush_on_read: bool = False,
        flush_on_write: bool = True,
        flush_on_delete: bool = True,
    ):
        self.backend = backend
        self.cache = InMemoryBackend()
        self.flush_interval = flush_interval

        self.flush_triggers: dict[OperationType, bool] = {
            "read": flush_on_read,
            "write": flush_on_write,
            "delete": flush_on_delete,
        }

        self.operations: list[Operation] = []
        self.last_flush = time.time()

        self.__class__._instances.add(self)

    def schedule_operation(
        self,
        op_type: OperationType,
        path: Path,
        value: Any | None = None,
    ) -> bool:
        self.operations.append(Operation(op_type, path, value))

        return self.check_flush(op_type)

    def check_flush(self, op_type: OperationType) -> bool:
        if not self.flush_triggers[op_type]:
            return False

        return time.time() - self.last_flush >= self.flush_interval


class CachingSyncBackend(Backend, CachingBackendBase[Backend]):
    def __init__(self, backend: Backend, **kwargs):
        super().__init__(backend, **kwargs)
        atexit.register(self.flush)

    def read(
        self,
        path: Path,
        default: _T = None,
    ) -> Any | _T:
        fake_default = Sentinel("fake_default")

        value = self.cache.read(path)

        if value is fake_default:
            value = self.backend.read(path, default)
            self.cache.write(path, value)

        if self.check_flush("read"):
            self.flush()

        return value

    def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None:
        self.cache.write(path, value)

        if self.schedule_operation("write", path, value):
            self.flush()

    def delete(self, path: Path) -> None:
        self.cache.delete(path)

        if self.schedule_operation("delete", path):
            self.flush()

    def flush(self) -> None:
        for operation in self.operations:
            if operation.type == "write":
                self.backend.write(operation.path, operation.value)
            elif operation.type == "delete":
                self.backend.delete(operation.path)

        self.operations.clear()
        self.last_flush = time.time()


class CachingAsyncBackend(AsyncBackend, CachingBackendBase[AsyncBackend]):
    def __init__(self, backend: AsyncBackend, **kwargs):
        super().__init__(backend, **kwargs)
        atexit.register(self._sync_flush)

    async def read(
        self,
        path: Path,
        default: _T = None,
    ) -> Any | _T:
        fake_default = Sentinel("fake_default")

        value = self.cache.read(path)

        if value is fake_default:
            value = await self.backend.read(path, default)
            self.cache.write(path, value)

        if self.check_flush("read"):
            await self.flush()

        return value

    async def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None:
        self.cache.write(path, value)

        if self.schedule_operation("write", path, value):
            await self.flush()

    async def delete(self, path: Path) -> None:
        self.cache.delete(path)

        if self.schedule_operation("delete", path):
            await self.flush()

    async def flush(self) -> None:
        operations = self.operations
        self.operations = []
        self.last_flush = time.time()

        for operation in operations:
            if operation.type == "write":
                await self.backend.write(operation.path, operation.value)
            elif operation.type == "delete":
                await self.backend.delete(operation.path)

    def _sync_flush(self):
        """Synchronous flush for cleanup on exit"""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.flush())
        finally:
            loop.close()
