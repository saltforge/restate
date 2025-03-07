import asyncio
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing_extensions import Any, Callable, Generic, Iterable, Literal, TypeVar
import json
import os
import aiofiles
import aiofiles.os as aio_os
import shutil

from restate.shared.constants import ROOT_PATH
from .base import Backend, AsyncBackend

_R = TypeVar("_R", str, bytes)
_C = TypeVar("_C", default=Any)
_T = TypeVar("_T")


@dataclass
class Serializer(Generic[_R, _C]):
    extension: str
    raw_type: type[_R]
    deserialize: Callable[[_R], _C]
    serialize: Callable[[_C], _R]

    @property
    def extension_fallback(self):
        fallback = ["bin", "txt"][self.raw_type is str]

        if not self.extension:
            return fallback

        return self.extension

    @property
    def suffix(self):
        return f".{self.extension_fallback}"

    @property
    def file_mode(self) -> Literal["b", "t"]:
        if self.raw_type is str:
            return "t"
        return "b"

    @property
    def write_mode(self) -> Literal["wb", "wt"]:
        return f"w{self.file_mode}"  # type: ignore

    @property
    def read_mode(self) -> Literal["rb", "rt"]:
        return f"r{self.file_mode}"  # type: ignore


json_serializer = Serializer(
    extension="json",
    raw_type=str,
    serialize=json.dumps,
    deserialize=json.loads,
)


class FileSystemBackendBase(Generic[_R]):
    def __init__(self, base_path: str | Path, serializer: Serializer[_R]):
        self.base_path = Path(base_path).absolute()
        self.serializer = serializer

    def get_fs_path(self, path: PurePosixPath) -> Path:
        relative = path.relative_to(ROOT_PATH)
        return self.base_path / relative

    def get_children_dir(self, path: PurePosixPath):
        return self.get_fs_path(path)

    def get_doc_path(self, path: PurePosixPath):
        return self.get_fs_path(path).with_suffix(self.serializer.suffix)

    def get_file_mode(self, write: bool = False):
        prefix = "rw"[write]

        if self.serializer.raw_type is str:
            return prefix

        return f"{prefix}b"


class FileSystemSyncBackend(FileSystemBackendBase, Backend):
    """
    Synchronous filesystem storage backend.

    Stores data in a directory structure with serialized files. Each path maps to both
    a possible document file and a directory for children. For example, for JSON serializer:

    ```
    /                        -> /
        users/               -> /users
            1.json           -> /users/1
            settings.json    -> /users/settings
            groups/          -> /users/groups
                admin.json   -> /users/groups/admin
    ```

    Features:
    - Configurable serialization format (JSON by default)
    - Automatic directory creation
    - Nested path support

    Args:
        base_path: Root directory for storage
        serializer: Serializer instance defining data format (defaults to JSON)

    Example:
        >>> backend = FileSystemSyncBackend("./storage")
        >>> backend.write("/users/1", {"name": "John"})
        >>> backend.read("/users/1")
        {'name': 'John'}
        >>> backend.read("/users")
        {'1': {'name': 'John'}}
    """

    def __init__(
        self,
        base_path: str | Path,
        serializer: Serializer[_R] = json_serializer,
    ):
        super().__init__(base_path, serializer)

    def ensure_parent_dirs(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def iter_children(self, path: PurePosixPath) -> Iterable[PurePosixPath]:
        children_dir = self.get_children_dir(path)

        if not children_dir.exists():
            return

        visited: set[PurePosixPath] = set()

        for filepath in children_dir.iterdir():
            if (filepath.suffix == self.serializer.suffix) or (
                filepath.suffix == "" and filepath.is_dir()
            ):
                child_path = path / filepath.name
            else:
                continue

            if child_path not in visited:
                visited.add(child_path)
                yield child_path

    def read(
        self,
        path: PurePosixPath,
        default: _T = None,
    ) -> Any | _T:
        doc_path = self.get_doc_path(path)

        resulting_data = {}

        if doc_path.exists():
            with open(doc_path, self.serializer.read_mode) as f:
                raw_data = f.read()

            resulting_data["/"] = self.serializer.deserialize(raw_data)

        for child_path in self.iter_children(path):
            resulting_data[child_path.name] = self.read(child_path)

        if not resulting_data:
            return default

        if len(resulting_data) == 1 and "/" in resulting_data:
            return resulting_data["/"]

        return resulting_data

    def write(
        self,
        path: PurePosixPath,
        value: Any | None,
    ) -> None:
        doc_path = self.get_doc_path(path)
        self.ensure_parent_dirs(doc_path)

        serialized = self.serializer.serialize(value)

        with open(doc_path, self.serializer.write_mode) as f:
            f.write(serialized)

    def delete(self, path: PurePosixPath) -> None:
        doc_path = self.get_doc_path(path)
        dir_path = self.get_children_dir(path)

        try:
            os.remove(doc_path)
        except Exception:
            pass

        try:
            shutil.rmtree(dir_path)
        except Exception:
            pass


class FileSystemAsyncBackend(FileSystemBackendBase, AsyncBackend):
    """
    Asynchronous filesystem storage backend.

    Identical to FileSystemSyncBackend in structure and features, but provides
    async interface using aiofiles for non-blocking I/O operations.

    Storage structure example for JSON serializer:

    ```
    /                        -> /
        users/               -> /users
            1.json           -> /users/1
            settings.json    -> /users/settings
            groups/          -> /users/groups
                admin.json   -> /users/groups/admin
    ```

    Features:
    - Configurable serialization format (JSON by default)
    - Automatic directory creation
    - Nested path support

    Args:
        base_path: Root directory for storage
        serializer: Serializer instance defining data format (defaults to JSON)

    Example:
        >>> backend = FileSystemAsyncBackend("./storage")
        >>> await backend.write("/users/1", {"name": "John"})
        >>> await backend.read("/users/1")
        {'name': 'John'}
        >>> await backend.read("/users")
        {'1': {'name': 'John'}}
    """

    async def __init__(
        self,
        base_path: str | Path,
        serializer: Serializer[_R] = json_serializer,
    ):
        super().__init__(base_path, serializer)

    async def ensure_parent_dirs(self, path: Path) -> None:
        await aio_os.makedirs(path.parent, exist_ok=True)

    async def iter_children(self, path: PurePosixPath) -> Iterable[PurePosixPath]:
        children_dir = self.get_children_dir(path)

        if not aio_os.path.exists(children_dir):
            return []

        children = await aio_os.listdir(children_dir)

        visited: set[PurePosixPath] = set()

        for filepath_str in children:
            filepath = Path(filepath_str)

            if (filepath.suffix == self.serializer.suffix) or (
                filepath.suffix == "" and filepath.is_dir()
            ):
                child_path = path / filepath.name
            else:
                continue

            if child_path not in visited:
                visited.add(child_path)

        return visited

    async def read(
        self,
        path: PurePosixPath,
        default: _T = None,
    ) -> Any | _T:
        doc_path = self.get_doc_path(path)

        resulting_data = {}

        if aio_os.path.exists(doc_path):
            async with aiofiles.open(doc_path, self.serializer.read_mode) as f:
                raw_data = await f.read()

            resulting_data["/"] = self.serializer.deserialize(raw_data)

        for child_path in await self.iter_children(path):
            resulting_data[child_path.name] = self.read(child_path)

        if not resulting_data:
            return default

        if len(resulting_data) == 1 and "/" in resulting_data:
            return resulting_data["/"]

        return resulting_data

    async def write(
        self,
        path: PurePosixPath,
        value: Any | None,
    ) -> None:
        doc_path = self.get_doc_path(path)
        await self.ensure_parent_dirs(doc_path)

        async with aiofiles.open(doc_path, self.serializer.write_mode) as f:
            await f.write(self.serializer.serialize(value))

    async def delete(self, path: PurePosixPath) -> None:
        doc_path = self.get_doc_path(path)
        dir_path = self.get_children_dir(path)

        try:
            await aio_os.remove(doc_path)
        except Exception:
            pass

        try:
            await asyncio.to_thread(
                shutil.rmtree,
                dir_path,
            )
        except Exception:
            pass
