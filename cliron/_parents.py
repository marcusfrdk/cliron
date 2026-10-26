import inspect
import os
import stat
import sys
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import FunctionType
from typing import ClassVar, Protocol, TextIO, final

from cliron._children import AnyChild, Child, check_below
from cliron._names import (
    check_parameter_name,
    check_short,
    check_variable,
    long_flag,
    placeholder,
)
from cliron._nodes import F, nodes_of, store

Loader = Callable[[str], str | Awaitable[str | None] | None]


class Parent(ABC):
    """
    A node that provides the value of one parameter of a command or group.

    Every parent is one, from ``option`` to ``env``. Subclass it to fill a
    parameter from somewhere else, implement ``load``, and put an instance
    above the function: ``@DotEnv("api_key")``. cliron converts the text with
    the parameter's annotation and runs the children below the parent, as it
    does for an environment variable.
    """

    name: str
    help: str | None

    def __init__(self, name: str, *, help: str | None = None) -> None:
        """
        Create the parent.

        :param name: The parameter's name, in snake_case.
        :param help: What the input is for, shown under Input in the help.
        :raises TypeError: If ``name`` or ``help`` isn't a string.
        :raises ValueError: If ``name`` isn't snake_case or is a Python keyword.
        """
        written = decorator_of(self)
        self.name = check_parameter_name(name, written)
        self.help = _check_help(help, written)

    @abstractmethod
    def load(self) -> str | Awaitable[str | None] | None:
        """
        Load the parameter's text. It may be ``async def``.

        :returns: The text, which cliron converts with the parameter's
            annotation, or ``None`` if there is none.
        """

    def label(self) -> str:
        """
        Name the input the way help and errors show it.

        :returns: The label, such as ``--keep`` or ``$API_KEY``. By default,
            the parameter's name.
        """
        return self.name

    def missing(self) -> str:
        """
        Say that a required input has no value.

        :returns: The error message, such as ``"--host is required."``.
        """
        return f"{self.label()} is required."

    @final
    def __call__(self, function: F) -> F:
        """
        Attach this parent to the function below it.

        :param function: The function of a command or group.
        :returns: The same function.
        :raises TypeError: If ``function`` isn't a function.
        """
        written = decorator_of(self)
        check_below(function, written)
        store(self, function, written)
        return function


class CommandLineParent(Parent):
    def load(self) -> None:
        return None


@dataclass(frozen=True)
class Argument(CommandLineParent):
    decorator: ClassVar[str] = "argument"
    name: str
    help: str | None = None

    def label(self) -> str:
        return placeholder(self.name)


@dataclass(frozen=True)
class Option(CommandLineParent):
    decorator: ClassVar[str] = "option"
    name: str
    short: str | None = None
    help: str | None = None

    def label(self) -> str:
        return _flag_label(self.name, self.short)


@dataclass(frozen=True)
class Flag(CommandLineParent):
    decorator: ClassVar[str] = "flag"
    name: str
    short: str | None = None
    help: str | None = None

    def label(self) -> str:
        return _flag_label(self.name, self.short)


@dataclass(frozen=True)
class Env(Parent):
    decorator: ClassVar[str] = "env"
    name: str
    variable: str
    help: str | None = None

    def load(self) -> str | None:
        return os.environ.get(self.variable) or None

    def label(self) -> str:
        return f"${self.variable}"

    def missing(self) -> str:
        return f"{self.label()} isn't set."


@dataclass(frozen=True)
class Stdin(Parent):
    decorator: ClassVar[str] = "stdin"
    name: str
    help: str | None = None

    def load(self) -> str | None:
        stream = sys.stdin
        if stream is None or _is_character_device(stream):
            return None
        return stream.read()

    def label(self) -> str:
        return "stdin"

    def missing(self) -> str:
        return f"{self.label()}: nothing was piped in."


class FunctionParent(Parent):
    def __init__(self, function: Loader, name: str, help: str | None) -> None:
        self.function: Loader = function
        super().__init__(name, help=help)

    def load(self) -> str | Awaitable[str | None] | None:
        return self.function(self.name)


class ParentFactory(Protocol):
    def __call__(self, name: str, *, help: str | None = None) -> Parent: ...


BUILT_IN_PARENTS = (Argument, Option, Flag, Env, Stdin)


def decorator_of(parent: Parent) -> str:
    if isinstance(parent, BUILT_IN_PARENTS):
        return parent.decorator
    if isinstance(parent, FunctionParent):
        return parent.function.__name__
    return type(parent).__name__


def load_function(parent: Parent) -> object:
    if isinstance(parent, FunctionParent):
        return parent.function
    return type(parent).load


def flags(parent: Parent) -> tuple[str, ...]:
    if not isinstance(parent, Option | Flag):
        return ()
    if parent.short is None:
        return (long_flag(parent.name),)
    return (long_flag(parent.name), parent.short)


def call(parent: Parent) -> str:
    return f'@{decorator_of(parent)}("{parent.name}")'


def parents_of(function: FunctionType) -> tuple[Parent, ...]:
    return tuple(record for record in nodes_of(function) if isinstance(record, Parent))


def children_of(function: FunctionType) -> dict[str, tuple[AnyChild, ...]]:
    attached: dict[str, list[AnyChild]] = {}
    current: str | None = None
    for record in nodes_of(function):
        if isinstance(record, Parent):
            current = record.name
            _ = attached.setdefault(current, [])
        if isinstance(record, Child):
            if current is None:
                message = (
                    f"@{record!r} is above every parent, so it has nothing to "
                    "check. Put it right below the parent whose value it checks."
                )
                raise TypeError(message)
            attached[current].append(record)
    return {name: tuple(children) for name, children in attached.items()}


def parent(function: Loader) -> ParentFactory:
    """
    Turn a function into a parent that loads a parameter's text.

    The function takes the parameter's name and returns its text, or ``None``
    if there is none: ``def git_branch(name: str) -> str | None`` is used as
    ``@git_branch("branch", help="The branch to deploy.")``. A parent with
    options of its own is a subclass of ``Parent``.

    :param function: The function, which takes the parameter's name.
    :returns: A function that takes the name and help, and returns the parent.
    :raises TypeError: If ``function`` isn't a function that takes the name as
        its only argument.
    """
    if not isinstance(function, FunctionType):
        message = (
            "@parent must decorate a function, such as "
            f"def git_branch(name: str) -> str | None, not {function!r}."
        )
        raise TypeError(message)
    try:
        _ = inspect.signature(function).bind("name")
    except TypeError:
        name = function.__name__
        message = (
            f"@parent function '{name}' must take the name as its only argument, "
            f"such as def {name}(name: str) -> str | None."
        )
        raise TypeError(message) from None

    def make(name: str, *, help: str | None = None) -> Parent:
        return FunctionParent(function, name, help)

    return make


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
    return Argument(
        check_parameter_name(name, "argument"), _check_help(help, "argument")
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
    return Option(
        check_parameter_name(name, "option"),
        check_short(short, "option"),
        _check_help(help, "option"),
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
    return Flag(
        check_parameter_name(name, "flag"),
        check_short(short, "flag"),
        _check_help(help, "flag"),
    )


def env(
    name: str, *, variable: str | None = None, help: str | None = None
) -> Callable[[F], F]:
    """
    Fill a parameter from an environment variable.

    The variable is the name in capitals: ``notes_db`` reads ``NOTES_DB``. A
    variable that is set to an empty value counts as not set.

    :param name: The parameter's name, in snake_case.
    :param variable: The variable to read instead, such as ``"GITHUB_TOKEN"``.
    :param help: What the variable is for, shown under Environment in the help.
    :returns: A decorator for the function of a command or group.
    :raises TypeError: If ``name``, ``variable`` or ``help`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case or is a Python keyword, or
        ``variable`` isn't letters, digits and underscores that don't start
        with a digit.
    """
    checked = check_parameter_name(name, "env")
    return Env(
        checked,
        check_variable(variable) or placeholder(checked),
        _check_help(help, "env"),
    )


def stdin(name: str, *, help: str | None = None) -> Callable[[F], F]:
    """
    Fill a parameter from the text piped into the program.

    Nothing is read from a terminal, so the program never waits for typing.
    One final line break is dropped, and a ``list`` or ``tuple`` gets one item
    per line.

    :param name: The parameter's name, in snake_case.
    :param help: What the input is for, shown under Input in the help.
    :returns: A decorator for the function of a command.
    :raises TypeError: If ``name`` or ``help`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case or is a Python keyword.
    """
    return Stdin(check_parameter_name(name, "stdin"), _check_help(help, "stdin"))


def _is_character_device(stream: TextIO) -> bool:
    try:
        mode = os.fstat(stream.fileno()).st_mode
    except (AttributeError, OSError, ValueError):
        return False
    return stat.S_ISCHR(mode)


def _flag_label(name: str, short: str | None) -> str:
    return long_flag(name) if short is None else f"{short}/{long_flag(name)}"


def _check_help(help: object, decorator: str) -> str | None:
    if help is None or isinstance(help, str):
        return help
    message = (
        f'@{decorator} takes help as a string, such as help="How many.", not {help!r}.'
    )
    raise TypeError(message)
