import inspect
import re
import typing
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import FunctionType
from typing import (
    ClassVar,
    Concatenate,
    Generic,
    Literal,
    Never,
    ParamSpec,
    Protocol,
    Self,
    TypeVar,
    final,
)

from cliron._conversion import describe, shown, value_type
from cliron._nodes import F, is_async, store

In_contra = TypeVar("In_contra", contravariant=True)
Out_co = TypeVar("Out_co", covariant=True)
T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")

Bound = int | float | date | time

_PATTERN_EXAMPLE = '@matches(r"[a-z]+")'
_BOUNDED: frozenset[object] = frozenset({int, float, date, datetime, time})
_NUMBERS: frozenset[object] = frozenset({int, float})
_EXACT: frozenset[object] = frozenset({int, date})


class _Ordered(Protocol):
    def __lt__(self, other: Self, /) -> bool: ...


class Child(ABC, Generic[In_contra, Out_co]):
    """
    A node that checks or changes the value of the parent above it.

    Subclass it with the types it takes and returns, such as
    ``Child[int, int]``, implement ``process``, and put an instance right
    below the parent: ``@Even()``. A first child that takes ``str`` gets the
    text from the command line, so it can convert it.

    :cvar default_check: When cliron runs the child on the parameter's
        default: ``"definition"`` checks it once, with the CLI's definition, and
        ``"run"`` checks it on each run that uses it, for a child whose answer
        depends on more than the value, such as on the files that exist.
    """

    default_check: ClassVar[Literal["definition", "run"]] = "definition"

    @abstractmethod
    def process(self, value: In_contra, /) -> Out_co | Awaitable[Out_co]:
        """
        Check or change a value.

        It may be ``async def``. The default of a child whose ``process`` is
        async is checked on each run that uses it, as with
        ``default_check = "run"``.

        :param value: The parent's value, or the text from the command line
            for a first child that takes ``str``.
        :returns: The value passed on to the next child or the function.
        :raises ValueError: If the value isn't valid, with a message that says
            why, such as ``"3 isn't even."``.
        """

    def describe(self) -> str | None:
        """
        Describe what this child accepts, for the help.

        :returns: A sentence added to the parameter's help, or ``None`` for
            nothing.
        """
        return None

    @final
    def __call__(self, function: F) -> F:
        """
        Attach this child to the parent right above it.

        :param function: The function of a command or group.
        :returns: The same function.
        :raises TypeError: If ``function`` isn't a function.
        """
        check_below(function, repr(self))
        store(self, function, repr(self))
        return function

    def __repr__(self) -> str:
        """
        Show the child as it is written below its parent, without the ``@``.

        :returns: The class name and parentheses, such as ``Even()``.
        """
        return f"{type(self).__qualname__}()"


AnyChild = Child[Never, object]


@dataclass(frozen=True, repr=False)
class Between(Child[Bound, Bound]):
    low: Bound | None
    high: Bound | None

    def process(self, value: Bound, /) -> Bound:
        below = self.low is not None and _less(value, self.low)
        above = self.high is not None and _less(self.high, value)
        if not (below or above):
            return value
        if self.low is not None and self.high is not None:
            problem = f"isn't between {shown(self.low)} and {shown(self.high)}"
        elif below:
            problem = f"is less than {shown(self.low)}"
        else:
            problem = f"is more than {shown(self.high)}"
        message = f"{_shown_value(value)} {problem}."
        raise ValueError(message)

    def describe(self) -> str | None:
        if self.low is not None and self.high is not None:
            return f"{shown(self.low)} to {shown(self.high)}."
        if self.low is not None:
            return f"At least {shown(self.low)}."
        return f"At most {shown(self.high)}."

    def misfit(self, base: object, name: str) -> str | None:
        if base not in _BOUNDED:
            return (
                f"@{self!r} checks numbers, dates or times, "
                f"but parameter {name!r} has the type {describe(base)}."
            )
        for bound in (self.low, self.high):
            if bound is not None and not _bound_fits(bound, base):
                return (
                    f"@{self!r} has {type(bound).__name__} bounds, but parameter "
                    f"{name!r} has the type {describe(base)}. "
                    f"Use {describe(base)} bounds."
                )
        return None

    def __repr__(self) -> str:
        return _bounds_text("between", repr(self.low), repr(self.high), self)


@dataclass(frozen=True, repr=False)
class Length(Child[str, str]):
    low: int | None
    high: int | None

    def process(self, value: str, /) -> str:
        size = len(value)
        short = self.low is not None and size < self.low
        long = self.high is not None and size > self.high
        if not (short or long):
            return value
        if self.low is not None and self.high is not None:
            problem = f"isn't between {self.low} and {self.high} characters long"
        elif short:
            problem = f"is shorter than {_characters(self.low)}"
        else:
            problem = f"is longer than {_characters(self.high)}"
        message = f"{value!r} {problem}."
        raise ValueError(message)

    def describe(self) -> str | None:
        if self.low is not None and self.high is not None:
            return f"{self.low} to {self.high} characters."
        if self.low is not None:
            return f"At least {_characters(self.low)}."
        return f"At most {_characters(self.high)}."

    def misfit(self, base: object, name: str) -> str | None:
        return _text_misfit(self, base, name)

    def __repr__(self) -> str:
        return _bounds_text("length", str(self.low), str(self.high), self)


@dataclass(frozen=True, repr=False)
class Matches(Child[str, str]):
    pattern: re.Pattern[str]

    def process(self, value: str, /) -> str:
        if self.pattern.fullmatch(value):
            return value
        message = f"{value!r} doesn't match {self.pattern.pattern}."
        raise ValueError(message)

    def describe(self) -> str | None:
        return f"Must match {self.pattern.pattern}."

    def misfit(self, base: object, name: str) -> str | None:
        return _text_misfit(self, base, name)

    def __repr__(self) -> str:
        return f'matches("{self.pattern.pattern}")'


@dataclass(frozen=True, repr=False)
class Choices(Child[object, object]):
    values: tuple[object, ...]
    text: str
    source: type[Enum] | None = None

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(shown(value) for value in self.values)

    def process(self, value: object, /) -> object:
        if value in self.values:
            return value
        message = f"{_shown_value(value)} isn't one of {', '.join(self.labels)}."
        raise ValueError(message)

    def misfit(self, base: object, name: str) -> str | None:
        source = self.source
        if source is not None:
            if base is source:
                return (
                    f"@{self!r} allows every member of {source.__qualname__}, "
                    "which the annotation already does. Remove it."
                )
            return (
                f"@{self!r} lists members of {source.__qualname__}, but parameter "
                f"{name!r} has the type {describe(base)}. "
                f"Annotate it as {source.__qualname__} instead."
            )
        for value in self.values:
            if typing.get_origin(base) is typing.Literal:
                literals: tuple[object, ...] = typing.get_args(base)
                if value not in literals:
                    allowed = ", ".join(repr(literal) for literal in literals)
                    return (
                        f"@{self!r} lists {value!r}, but parameter {name!r} "
                        f"only takes {allowed}."
                    )
            elif not _value_fits(value, base):
                return (
                    f"@{self!r} lists {value!r}, a {type(value).__name__}, but "
                    f"parameter {name!r} has the type {describe(base)}. "
                    f"Use {describe(base)} values."
                )
        return None

    def __repr__(self) -> str:
        return self.text


BUILT_IN_KINDS = (Between, Length, Matches, Choices)


@dataclass(frozen=True, repr=False)
class FunctionChild(Child[T, R]):
    function: Callable[..., R]
    name: str
    arguments: tuple[object, ...]
    keywords: tuple[tuple[str, object], ...]

    def process(self, value: T, /) -> R:
        return self.function(value, *self.arguments, **dict(self.keywords))

    def __repr__(self) -> str:
        shown_arguments = [repr(argument) for argument in self.arguments]
        shown_arguments += [f"{key}={value!r}" for key, value in self.keywords]
        return f"{self.name}({', '.join(shown_arguments)})"


def child(function: Callable[Concatenate[T, P], R]) -> Callable[P, Child[T, R]]:
    """
    Turn a function into a child that checks or changes a parent's value.

    The function takes the value first, and its other parameters become the
    child's options: ``def slug(value: str, separator: str = "-") -> str`` is
    used as ``@slug()`` or ``@slug(separator="_")`` right below a parent. It
    returns the value passed on, or raises ``ValueError`` with a message that
    says why the value isn't valid.

    :param function: The function, which takes the value as its first
        parameter.
    :returns: A function that takes the options and returns the child.
    :raises TypeError: If ``function`` isn't a function, or doesn't take the
        value as its first parameter.
    """
    if not isinstance(function, FunctionType):
        message = (
            f"@child must decorate a function, such as def slug(value: str) -> str, "
            f"not {function!r}."
        )
        raise TypeError(message)
    name = function.__name__
    signature = inspect.signature(function)
    first = next(iter(signature.parameters.values()), None)
    if first is None or first.kind not in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }:
        message = (
            f"@child function '{name}' must take the value as its first "
            f"parameter, such as def {name}(value: str) -> str."
        )
        raise TypeError(message)

    def options(*arguments: P.args, **keywords: P.kwargs) -> Child[T, R]:
        try:
            _ = signature.bind(None, *arguments, **keywords)
        except TypeError as error:
            bare = len(arguments) == 1 and isinstance(arguments[0], FunctionType)
            if bare and not keywords:
                message = f"@{name} needs parentheses: @{name}()."
            else:
                message = f"@{name}: {error}."
            raise TypeError(message) from None
        return FunctionChild(function, name, arguments, tuple(keywords.items()))

    return options


def between(
    low: float | date | time | None = None,
    high: float | date | time | None = None,
) -> Callable[[F], F]:
    """
    Check that the value above lies between two bounds, both included.

    One bound alone leaves the other side open: ``between(low=1)`` allows
    [1, ∞) and ``between(high=100)`` allows (-∞, 100]. It checks ``int``,
    ``float``, ``date``, ``datetime`` and ``time`` values, with bounds of the
    same kind.

    :param low: The smallest value allowed.
    :param high: The largest value allowed.
    :returns: A decorator that goes right below the parent whose value it
        checks.
    :raises TypeError: If a bound isn't a number, date or time, the bounds are
        of different kinds, or neither bound is given.
    :raises ValueError: If ``low`` is above ``high``.
    """
    _check_parentheses(low, "between", "its bounds", "@between(1, 100)")
    found = Between(_bound(low), _bound(high))
    if low is None and high is None:
        message = "@between needs a bound, such as @between(1, 100) or @between(low=1)."
        raise TypeError(message)
    if low is not None and high is not None:
        if _kind(low) != _kind(high):
            message = (
                f"@{found!r} mixes bound types. "
                "Use two numbers, two dates or two times."
            )
            raise TypeError(message)
        if _less(high, low):
            _wrong_way_round(found, Between(high, low))
    return found


def length(low: int | None = None, high: int | None = None) -> Callable[[F], F]:
    """
    Check that the text above has a number of characters between two bounds.

    Both bounds are included, and one bound alone leaves the other side open:
    ``length(low=1)`` allows any text that isn't empty, and
    ``length(high=20)`` allows at most 20 characters.

    :param low: The fewest characters allowed, 1 or more.
    :param high: The most characters allowed, 1 or more.
    :returns: A decorator that goes right below the parent whose text it
        checks.
    :raises TypeError: If a bound isn't a whole number, or neither bound is
        given.
    :raises ValueError: If a bound is below 1, or ``low`` is above ``high``.
    """
    _check_parentheses(low, "length", "its bounds", "@length(3, 20)")
    found = Length(_size(low), _size(high))
    if low is None and high is None:
        message = "@length needs a bound, such as @length(3, 20) or @length(low=1)."
        raise TypeError(message)
    if low is not None and high is not None and high < low:
        _wrong_way_round(found, Length(high, low))
    return found


def matches(pattern: str) -> Callable[[F], F]:
    """
    Check that the whole text above matches a regular expression.

    :param pattern: The regular expression, such as ``r"[a-z0-9-]+"``.
    :returns: A decorator that goes right below the parent whose text it
        checks.
    :raises TypeError: If ``pattern`` isn't a string.
    :raises ValueError: If ``pattern`` isn't a valid regular expression.
    """
    text = _pattern_text(pattern)
    try:
        compiled = re.compile(text)
    except re.error as error:
        message = f'@matches("{text}") isn\'t a valid pattern: {error}.'
        raise ValueError(message) from None
    return Matches(compiled)


def choices(*values: object) -> Callable[[F], F]:
    """
    Check that the value above is one of several values.

    Give the values one by one, such as ``choices("zip", "tar")``, or one
    list, tuple, set or frozenset of them. Help lists them in place of the
    value's placeholder. For an Enum, annotate the parameter with it, and use
    ``choices`` to allow only some of its members.

    :param values: The values allowed, of the parameter's type.
    :returns: A decorator that goes right below the parent whose value it
        checks.
    :raises TypeError: If no values are given, a range or an Enum is given
        where values belong, or a collection is mixed with values.
    :raises ValueError: If a value is given twice.
    """
    return _choices(values)


def check_below(function: object, decorator: str) -> None:
    if isinstance(function, Child):
        name = written_name(function)
        message = f"@{decorator} is above @{name}, which needs parentheses: @{name}()."
        raise TypeError(message)


def run_child(found: AnyChild, value: object) -> object:
    return typing.cast("Child[object, object]", found).process(value)


def checks_on_run(found: AnyChild) -> bool:
    return found.default_check == "run" or is_async(child_function(found))


def child_function(found: AnyChild) -> object:
    if isinstance(found, FunctionChild):
        return typing.cast("FunctionChild[object, object]", found).function
    return type(found).process


def input_type(found: AnyChild) -> object:
    process: Callable[..., object] = (
        typing.cast("FunctionChild[object, object]", found).function
        if isinstance(found, FunctionChild)
        else found.process
    )
    hints: dict[str, object] = typing.get_type_hints(process)
    first = next(iter(inspect.signature(process).parameters))
    return hints.get(first)


def written_name(found: object) -> str:
    if isinstance(found, FunctionChild):
        return typing.cast("FunctionChild[object, object]", found).name
    return type(found).__name__


def converts(children: tuple[AnyChild, ...], annotation: object) -> bool:
    if not children or isinstance(children[0], BUILT_IN_KINDS):
        return False
    return _same(input_type(children[0]), str) and not _same(
        value_type(annotation), str
    )


def misfit(found: AnyChild, base: object, name: str) -> str | None:
    if isinstance(found, BUILT_IN_KINDS):
        return found.misfit(base, name)
    taken = input_type(found)
    if fits(base, taken):
        return None
    return (
        f"@{found!r} takes {describe(taken)}, "
        f"but parameter {name!r} has the type {describe(base)}."
    )


def fits(base: object, taken: object) -> bool:
    if not isinstance(base, type) or not isinstance(taken, type):
        return True
    return issubclass(base, taken) or (_same(base, int) and _same(taken, float))


def _choices(values: tuple[object, ...]) -> Choices:
    if len(values) == 1:
        only = values[0]
        _check_parentheses(only, "choices", "its values", '@choices("zip", "tar")')
        if isinstance(only, range):
            raise _range_error(only)
        if isinstance(only, type) and issubclass(only, Enum):
            return _checked_choices(tuple(only), f"choices({only.__qualname__})", only)
        if isinstance(only, list | tuple | set | frozenset):
            items = tuple(typing.cast("Collection[object]", only))
            if isinstance(only, set | frozenset):
                items = tuple(sorted(items, key=shown))
            listed = ", ".join(_quoted(item) for item in items)
            return _checked_choices(items, f"choices([{listed}])")
    text = f"choices({', '.join(_quoted(value) for value in values)})"
    for value in values:
        if isinstance(value, list | tuple | set | frozenset | range) or (
            isinstance(value, type) and issubclass(value, Enum)
        ):
            message = (
                f"@{text} mixes a collection with values. "
                "Pass the values one by one, or one collection."
            )
            raise TypeError(message)
    return _checked_choices(values, text)


def _checked_choices(
    values: tuple[object, ...], text: str, source: type[Enum] | None = None
) -> Choices:
    if not values:
        message = '@choices needs values, such as @choices("zip", "tar").'
        raise TypeError(message)
    for value in values:
        if values.count(value) > 1:
            message = f"@{text} lists {value!r} twice. Remove one."
            raise ValueError(message)
    return Choices(values, text, source)


def _range_error(values: range) -> TypeError:
    if values.step == 1:
        fix = f"Use @between({values.start}, {values.stop - 1}) instead."
    else:
        fix = f"List its values with @choices(*{values!r})."
    return TypeError(f"@choices takes no range. {fix}")


def _check_parentheses(value: object, decorator: str, what: str, example: str) -> None:
    if isinstance(value, FunctionType):
        message = f"@{decorator} needs {what} in parentheses, such as {example}."
        raise TypeError(message)


def _bound(value: object) -> Bound | None:
    if value is None or (
        isinstance(value, int | float | date | time) and not isinstance(value, bool)
    ):
        return value
    message = (
        "@between takes numbers, dates or times as bounds, "
        f"such as @between(1, 100), not {value!r}."
    )
    raise TypeError(message)


def _size(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        message = (
            "@length takes whole numbers as bounds, "
            f"such as @length(3, 20), not {value!r}."
        )
        raise TypeError(message)
    if value < 1:
        message = (
            f"@length takes bounds of 1 or more, such as @length(1, 20), not {value}."
        )
        raise ValueError(message)
    return value


def _pattern_text(pattern: object) -> str:
    _check_parentheses(pattern, "matches", "a pattern", _PATTERN_EXAMPLE)
    if isinstance(pattern, str):
        return pattern
    message = (
        f"@matches takes a pattern as a string, such as {_PATTERN_EXAMPLE}, "
        f"not {pattern!r}."
    )
    raise TypeError(message)


def _wrong_way_round(found: AnyChild, swapped: AnyChild) -> None:
    message = f"@{found!r} has its bounds the wrong way round. Use @{swapped!r}."
    raise ValueError(message)


def _bounds_text(decorator: str, low: str, high: str, found: Between | Length) -> str:
    if found.low is not None and found.high is not None:
        return f"{decorator}({low}, {high})"
    if found.low is not None:
        return f"{decorator}(low={low})"
    return f"{decorator}(high={high})"


def _kind(bound: Bound) -> str:
    if isinstance(bound, datetime):
        return "datetime"
    if isinstance(bound, date | time):
        return type(bound).__name__
    return "number"


def _bound_fits(bound: Bound, base: object) -> bool:
    if _same(base, float):
        return type(bound) in _NUMBERS
    return _same(type(bound), base)


def _value_fits(value: object, base: object) -> bool:
    if _same(base, float):
        return type(value) in _NUMBERS
    if base in _EXACT:
        return _same(type(value), base)
    return isinstance(base, type) and isinstance(value, base)


def _text_misfit(found: AnyChild, base: object, name: str) -> str | None:
    if base is str:
        return None
    return (
        f"@{found!r} checks text, but parameter {name!r} has the type {describe(base)}."
    )


def _characters(count: int | None) -> str:
    return f"{count} character" if count == 1 else f"{count} characters"


def _shown_value(value: object) -> str:
    if isinstance(value, str | Enum | Path):
        return repr(shown(value))
    return shown(value)


def _quoted(value: object) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, type):
        return value.__qualname__
    if isinstance(value, Enum):
        return f"{type(value).__qualname__}.{value.name}"
    return repr(value)


def _same(left: object, right: object) -> bool:
    return left is right


def _less(left: object, right: object) -> bool:
    return typing.cast("_Ordered", left) < typing.cast("_Ordered", right)
