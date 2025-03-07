from __future__ import annotations

from pathlib import PurePosixPath as Path
from typing_extensions import Any, TypeVar

_T = TypeVar("_T")


class Backend:
    def read(
        self,
        path: Path,
        default: _T = None,
    ) -> Any | _T: ...

    def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None: ...

    def delete(self, path: Path) -> None: ...


class AsyncBackend:
    async def read(
        self,
        path: Path,
        default: Any | _T = None,
    ) -> Any | _T: ...

    async def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None: ...

    async def delete(self, path: Path) -> None: ...
