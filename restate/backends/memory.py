from __future__ import annotations

from pathlib import PurePath
from typing_extensions import Any, TypeAlias, TypeVar
from restate.shared.constants import ROOT_PATH
from restate.shared.sentinel import Sentinel
from .base import Backend


NestedStore: TypeAlias = dict

NESTED_KEY = Sentinel("nested")

_T = TypeVar("_T")


class InMemoryBackend(Backend):
    """
    In-memory storage.
    Fast, responsive, but loses all state on restart.
    """

    def __init__(self):
        self.stores: dict[PurePath, Store] = {ROOT_PATH: Store(self, ROOT_PATH)}

    def get_or_create_store(self, path: PurePath) -> Store:
        if path not in self.stores:
            self.stores[path] = Store(self, path)

            parent_store = self.get_or_create_store(path.parent)
            parent_store.children.add(path)

        return self.stores[path]

    def get_store(self, path: PurePath) -> Store | None:
        return self.stores.get(path)

    def read(
        self,
        path: PurePath,
        default: _T = None,
    ) -> Any | _T:
        store = self.get_store(path)

        if not store:
            return default

        return store.data

    def write(self, path: PurePath, value: Any | None) -> None:
        store = self.get_or_create_store(path)
        store.set_value(value)

    def delete(self, path: PurePath) -> None:
        store = self.get_store(path)

        if not store:
            return

        for child_path in store.children:
            self.delete(child_path)

        if path != ROOT_PATH:  # do not delete root
            self.stores.pop(path)


class Store:
    def __init__(self, backend: InMemoryBackend, path: PurePath) -> None:
        self.path = path
        self.children: set[PurePath] = set()
        self.backend = backend
        self._has_value: bool = False
        self._value: Any = None

    def set_value(self, value: Any) -> None:
        self._has_value = True
        self._value = value

    @property
    def data(self):
        if not self.children:
            if self._has_value:
                return self._value

            return {}

        resulting_data = {}

        if self._has_value:
            resulting_data["/"] = self._value

        for child_path in self.children:
            data = self.backend.read(child_path)

            if child_path.is_relative_to(self.path):
                child_path = child_path.relative_to(self.path)

            resulting_data[str(child_path)] = data

        return resulting_data

    def __repr__(self) -> str:
        fields = {
            "path": self.path,
            "value": self._value if self._has_value else "-",
            "children": len(self.children),
        }

        return f"Store({', '.join(f'{k}: {v}' for k,v in fields.items())})"
