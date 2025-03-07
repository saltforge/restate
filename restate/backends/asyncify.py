from pathlib import PurePosixPath as Path
from typing_extensions import Any
from restate.backends.base import AsyncBackend, Backend


class AsyncifyBackend(AsyncBackend):
    """
    This backend "converts" any sync backend into async one.
    This will not magically make your blocking calls non-blocking, this is just interface compat.
    Used internally by async controller.
    """

    def __init__(self, sync_backend: Backend):
        self.sync_backend = sync_backend

    async def read(
        self,
        path: Path,
        default: Any | None = None,
    ) -> Any | None:
        return self.sync_backend.read(path, default)

    async def write(self, path: Path, value: Any | None) -> None:
        return self.sync_backend.write(path, value)

    async def delete(self, path: Path) -> None:
        return self.sync_backend.delete(path)
