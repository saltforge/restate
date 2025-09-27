from typing import Any, Generic, TypeVar
from restate.controllers.internal_types import PathLike

_T = TypeVar("_T", default=Any)


class BaseAtom(Generic[_T]):
    default: _T
    path: PathLike
