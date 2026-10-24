from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType
from typing import ClassVar, TypeVar, cast

from cliron._names import check_parameter_name, check_short, long_flag, placeholder

F = TypeVar("F", bound=Callable[..., object])

_PARENTS = "__cliron_parents__"


@dataclass(frozen=True)
class Argument:
    decorator: ClassVar[str] = "argument"
    name: str
    help: str | None = None


@dataclass(frozen=True)
class Option:
    decorator: ClassVar[str] = "option"
    name: str
    short: str | None = None
    help: str | None = None


@dataclass(frozen=True)
class Flag:
    decorator: ClassVar[str] = "flag"
    name: str
    short: str | None = None
    help: str | None = None


Parent = Argument | Option | Flag


def display(parent: Parent) -> str:
    if isinstance(parent, Argument):
        return placeholder(parent.name)
    return long_flag(parent.name)


def flags(parent: Parent) -> tuple[str, ...]:
    if isinstance(parent, Argument):
        return ()
    if parent.short is None:
        return (long_flag(parent.name),)
    return (long_flag(parent.name), parent.short)


def call(parent: Parent) -> str:
    return f'@{parent.decorator}("{parent.name}")'


def parents_of(function: FunctionType) -> tuple[Parent, ...]:
    return cast("tuple[Parent, ...]", vars(function).get(_PARENTS, ()))


def _attach(parent: Parent) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        _store(parent, function)
        return function

    return decorate


def argument(name: str, *, help: str | None = None) -> Callable[[F], F]:
    """
    Fill a parameter from a word on the command line.

    Arguments are filled in the order they are declared. A ``list`` or ``tuple``
    argument takes every remaining word, so it must come last.

    :param name: The parameter's name, in snake_case. Help and errors show it in
        capitals, such as ``NAME``.
    :param help: What the argument is for, shown in the command's help.
    :returns: A decorator for the function of a command.
    :raises TypeError: If ``name`` or ``help`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case or is a Python keyword.
    """
    return _attach(
        Argument(check_parameter_name(name, "argument"), _check_help(help, "argument"))
    )


def option(
    name: str, short: str | None = None, *, help: str | None = None
) -> Callable[[F], F]:
    """
    Fill a parameter from an option that takes a value, such as ``--count 3``.

    :param name: The parameter's name, in snake_case. The long flag is derived
        from it: ``dry_run`` becomes ``--dry-run``.
    :param short: A short flag, such as ``"-c"``.
    :param help: What the option is for, shown in the help.
    :returns: A decorator for the function of a command or group.
    :raises TypeError: If ``name``, ``short`` or ``help`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case or is a Python keyword, or
        ``short`` isn't a dash and one ASCII letter.
    """
    return _attach(
        Option(
            check_parameter_name(name, "option"),
            check_short(short),
            _check_help(help, "option"),
        )
    )


def flag(
    name: str, short: str | None = None, *, help: str | None = None
) -> Callable[[F], F]:
    """
    Fill a parameter from a flag that takes no value, such as ``--verbose``.

    A ``bool`` parameter is ``False`` until the flag is passed. An ``int``
    parameter counts how often it was passed, so ``-vvv`` is ``3``.

    :param name: The parameter's name, in snake_case. The long flag is derived
        from it: ``dry_run`` becomes ``--dry-run``.
    :param short: A short flag, such as ``"-v"``.
    :param help: What the flag is for, shown in the help.
    :returns: A decorator for the function of a command or group.
    :raises TypeError: If ``name``, ``short`` or ``help`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case or is a Python keyword, or
        ``short`` isn't a dash and one ASCII letter.
    """
    return _attach(
        Flag(
            check_parameter_name(name, "flag"),
            check_short(short),
            _check_help(help, "flag"),
        )
    )


def _check_help(help: object, decorator: str) -> str | None:
    if help is None or isinstance(help, str):
        return help
    message = (
        f'@{decorator} takes help as a string, such as help="How many.", not {help!r}.'
    )
    raise TypeError(message)


def _store(parent: Parent, function: object) -> None:
    if not isinstance(function, FunctionType):
        message = (
            f"@{parent.decorator} must decorate a function, "
            "so it goes below @command or @group."
        )
        raise TypeError(message)
    vars(function)[_PARENTS] = (parent, *parents_of(function))
