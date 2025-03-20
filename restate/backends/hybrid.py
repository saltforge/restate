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

    def get_subpaths(self, root_path: Path) -> list[Path]:
        subpaths: list[Path] = []

        for mount in self.mounts:
            if mount == root_path:
                continue

            if mount.is_relative_to(root_path):
                subpaths.append(mount)

        # this bit is important
        # we should work with shortest paths first to not overwrite children
        return sorted(subpaths, key=lambda p: len(p.parts))


class HybridSyncBackend(Backend, HybridBackendBase[Backend]):
    def read(
        self,
        path: Path,
        default: _T = None,
    ) -> Any | _T:
        local_path, backend = self.resolve_backend(path)
        base = backend.read(local_path, default)

        subpaths = self.get_subpaths(path)

        if isinstance(base, dict):
            for subpath in subpaths:
                store = base

                data = self.read(subpath)

                if data is None:
                    continue

                path_parts = list(
                    filter(
                        None,
                        (part.strip("/") for part in subpath.relative_to(path).parts),
                    )
                )

                if not path_parts:
                    # mounted path is the same as local?, we just rewrite the base
                    # shouldn't happen normally but

                    if isinstance(data, dict):
                        base = data

                    continue

                for part in path_parts[:-1]:
                    if not part.strip("/"):
                        continue

                    store[part] = {}
                    store = store[part]

                store[path_parts[-1]] = data

        return base

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
        base = await backend.read(local_path, default)

        if isinstance(base, dict):
            subpaths = self.get_subpaths(path)

            for subpath in subpaths:
                store = base

                data = await self.read(subpath)

                if data is None:
                    continue

                path_parts = list(
                    filter(
                        None,
                        (part.strip("/") for part in subpath.relative_to(path).parts),
                    )
                )

                if not path_parts:
                    # mounted path is the same as local?, we just rewrite the base
                    # shouldn't happen normally but

                    if isinstance(data, dict):
                        base = data

                    continue

                for part in path_parts[:-1]:
                    if not part.strip("/"):
                        continue

                    store[part] = {}
                    store = store[part]

                store[path_parts[-1]] = data

        return base

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
