from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType, MethodType
from typing import Literal

from cliron._children import check_below
from cliron._nodes import F, nodes_of, store
from cliron._parents import Parent, call

EventName = Literal["start", "success", "exit", "error"]


@dataclass(frozen=True, repr=False)
class Event:
    name: EventName

    def __repr__(self) -> str:
        return f"on.{self.name}()"


class On:
    """The events a hook runs on, such as ``on.start()``."""

    def start(self) -> Event:
        """
        Run before the command or group, and before anything inside a group.

        :returns: The event.
        """
        return Event("start")

    def success(self) -> Event:
        """
        Run after the command or group succeeded, a group's teardown included.

        :returns: The event.
        """
        return Event("success")

    def exit(self) -> Event:
        """
        Run after the command or group, whether it succeeded or failed.

        It runs exactly when the node's start hooks ran, like ``finally``.

        :returns: The event.
        """
        return Event("exit")

    def error(self) -> Event:
        """
        Handle an exception that leaves the command or group.

        The hook's function takes the exception as the parameter annotated
        with the exceptions it handles, such as ``exc: FileNotFoundError``,
        and runs for the first matching handler on the node. It covers the
        node's start hooks, its function and everything inside a group. When
        it returns, the exception is handled: a command's handler's value
        becomes the command's result, and a group's handler returns ``None``.
        When it raises, the exception goes on to the nodes outside.

        :returns: The event.
        """
        return Event("error")


on = On()


@dataclass(frozen=True, repr=False)
class Hook:
    event: Event
    callback: FunctionType

    def __call__(self, function: F) -> F:
        written = repr(self)
        check_below(function, written)
        store(self, function, written)
        return function

    def __repr__(self) -> str:
        return f"hook({self.event!r}, {self.callback.__name__})"


@dataclass(frozen=True)
class HookCall:
    hook: Hook
    injected: dict[str, type[object]]
    exception: tuple[str, tuple[type[Exception], ...]] | None = None


def hook(event: Event, callback: Callable[..., object]) -> Callable[[F], F]:
    """
    Run a function when an event happens around the command or group above.

    Like the other decorators, a hook attaches to the nearest node above it,
    so it goes right below ``@command`` or ``@group``, above the first parent.
    Its function receives ``Context`` and ``@state`` classes by annotation, as
    a command's does, and returns ``None``.

    :param event: When to run, such as ``on.start()``.
    :param callback: The function to run.
    :returns: A decorator that goes right below ``@command`` or ``@group``.
    :raises TypeError: If ``event`` isn't an event, or ``callback`` isn't a
        function.
    """
    return Hook(_checked_event(event), _checked_callback(callback))


def hooks_of(function: FunctionType) -> tuple[Hook, ...]:
    found: list[Hook] = []
    above: object = None
    for record in nodes_of(function):
        if not isinstance(record, Hook):
            above = record
            continue
        if above is not None:
            written = call(above) if isinstance(above, Parent) else f"@{above!r}"
            message = (
                f"@{record!r} is below {written}, so it would attach to it, "
                f"but {record.event!r} runs around commands and groups. "
                "Move it right below @command or @group, above the first parent."
            )
            raise TypeError(message)
        found.append(record)
    return tuple(found)


def _checked_event(event: object) -> Event:
    if isinstance(event, Event):
        return event
    if isinstance(event, MethodType) and event.__self__ is on:
        message = f"@hook needs the event called, such as on.{event.__name__}()."
    else:
        message = f"@hook takes an event first, such as on.start(), not {event!r}."
    raise TypeError(message)


def _checked_callback(callback: object) -> FunctionType:
    if isinstance(callback, FunctionType):
        return callback
    message = (
        "@hook takes a function to run, such as hook(on.start(), start_timer), "
        f"not {callback!r}."
    )
    raise TypeError(message)
