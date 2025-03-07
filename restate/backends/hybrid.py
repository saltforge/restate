from pathlib import PurePosixPath as Path
from typing_extensions import Any, Generic, Union, TypeVar

from restate.shared.constants import ROOT_PATH
from .base import Backend, AsyncBackend


_B = TypeVar("_B", bound=Union[Backend, AsyncBackend])
_T = TypeVar("_T")


class HybridBackendBase(Generic[_B]):
    def __init__(self, root_backend: _B):
        self.mounts: dict[Path, _B] = {}
        self.mount(ROOT_PATH, root_backend)

    def resolve_path(self, path: Path | str) -> Path:
        return ROOT_PATH / str(path).lstrip("/")

    def mount(self, path: Path | str, backend: _B):
        path = self.resolve_path(path)

        self.mounts[path] = backend

    def unmount(self, path: Path | str) -> _B | None:
        path = self.resolve_path(path)

        return self.mounts.pop(path, None)

    def resolve_backend(self, path: Path) -> tuple[Path, _B]:
        viable_paths = [
            mount_path for mount_path in self.mounts if path.is_relative_to(mount_path)
        ]

        viable_paths.sort(key=lambda path: len(path.parts), reverse=True)

        best_mount = viable_paths[0]

        return (
            ROOT_PATH / path.relative_to(best_mount),
            self.mounts[best_mount],
        )


class HybridSyncBackend(Backend, HybridBackendBase[Backend]):
    def read(
        self,
        path: Path,
        default: _T = None,
    ) -> Any | _T:
        local_path, backend = self.resolve_backend(path)
        return backend.read(local_path)

    def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None:
        local_path, backend = self.resolve_backend(path)
        return backend.write(local_path, value)

    def delete(self, path: Path) -> None:
        local_path, backend = self.resolve_backend(path)
        return backend.delete(local_path)


class HybridAsyncBackend(AsyncBackend, HybridBackendBase[AsyncBackend]):
    async def read(
        self,
        path: Path,
        default: _T = None,
    ) -> Any | _T:
        local_path, backend = self.resolve_backend(path)
        return await backend.read(local_path)

    async def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None:
        local_path, backend = self.resolve_backend(path)
        return await backend.write(local_path, value)

    async def delete(self, path: Path) -> None:
        local_path, backend = self.resolve_backend(path)
        return await backend.delete(local_path)
