from collections.abc import Callable
from types import FunctionType
from typing import TypeVar, cast

F = TypeVar("F", bound=Callable[..., object])

_NODES = "__cliron_nodes__"


def store(record: object, function: object, decorator: str) -> None:
    if not isinstance(function, FunctionType):
        message = (
            f"@{decorator} must decorate a function, "
            "so it goes below @command or @group."
        )
        raise TypeError(message)
    vars(function)[_NODES] = (record, *nodes_of(function))


def nodes_of(function: FunctionType) -> tuple[object, ...]:
    return cast("tuple[object, ...]", vars(function).get(_NODES, ()))
