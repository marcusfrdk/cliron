import inspect
import typing
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")

_STATES: "weakref.WeakSet[type[object]]" = weakref.WeakSet()
_SHARED_BY_EVERY_RUN: tuple[type[object], ...] = (list, dict, set)


@dataclass(frozen=True)
class Context:
    """
    What cliron knows about the run that a function is part of.

    A parameter of a command's or group's function that is annotated
    ``Context`` receives it, whatever the parameter is called, and every
    function in a run receives the same one.

    :ivar path: The command line's path to what runs, as users typed it, such
        as ``("notes", "tags", "rename-tag")``.
    :ivar values: The values of each command and group on the path, in the
        same order, by parameter name: ``ctx.values[-1]`` is the command's.
    """

    path: tuple[str, ...]
    values: tuple[Mapping[str, object], ...]


def state(cls: type[T]) -> type[T]:
    """
    Make a class hold your own data during a run.

    A parameter of a command's or group's function that is annotated with the
    class receives the run's one instance of it, whatever the parameter is
    called. cliron creates the instance without arguments when a function first
    asks for it, so every function in a run shares it, and the next run starts
    with a new one. A field without a default stays unset until a function sets
    it.

    :param cls: The class, which must work without arguments.
    :returns: The same class.
    :raises TypeError: If ``cls`` isn't a class, needs arguments, or has a
        field that defaults to a list, dict or set, which every run would share.
    """
    _STATES.add(_checked_state(cls))
    return cls


def injected(annotation: object) -> type[object] | None:
    if annotation is Context:
        return Context
    if isinstance(annotation, type) and annotation in _STATES:
        return annotation
    return None


def _checked_state(cls: object) -> type[object]:
    if not isinstance(cls, type):
        message = f"@state must decorate a class, such as class Notes:, not {cls!r}."
        raise TypeError(message)
    name = cls.__name__
    try:
        signature = inspect.signature(cls)
    except ValueError:
        signature = None
    if signature is not None:
        try:
            _ = signature.bind()
        except TypeError as error:
            message = (
                f"@state class {name} must work without arguments, but {error}. "
                "Give each of its fields a default, or none."
            )
            raise TypeError(message) from None
    for klass in cls.__mro__:
        attributes = typing.cast("Mapping[str, object]", vars(klass))
        for field, value in attributes.items():
            kind = type(value)
            if not field.startswith("__") and issubclass(kind, _SHARED_BY_EVERY_RUN):
                message = (
                    f"{name}.{field} defaults to a {kind.__name__}, which "
                    "every run would share. Leave it without a default and set "
                    "it in a function."
                )
                raise TypeError(message)
    return cls
