from __future__ import annotations

from pathlib import PurePosixPath as Path
from typing_extensions import Any


class Backend:
    def read(
        self,
        path: Path,
        default: Any | None = None,
    ) -> Any | None: ...

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
        default: Any | None = None,
    ) -> Any | None: ...

    async def write(
        self,
        path: Path,
        value: Any | None,
    ) -> None: ...

    async def delete(self, path: Path) -> None: ...
