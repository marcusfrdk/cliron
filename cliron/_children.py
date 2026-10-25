import re
import typing
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from types import FunctionType
from typing import ClassVar, Protocol, Self

from cliron._conversion import describe, shown
from cliron._nodes import F, nodes_of, store
from cliron._parents import PARENT_KINDS

Bound = int | float | date | time

_PATTERN_EXAMPLE = '@matches(r"[a-z]+")'
_BOUNDED: frozenset[object] = frozenset({int, float, date, datetime, time})
_NUMBERS: frozenset[object] = frozenset({int, float})
_EXACT: frozenset[object] = frozenset({int, date})


class _Ordered(Protocol):
    def __lt__(self, other: Self, /) -> bool: ...


@dataclass(frozen=True)
class Between:
    decorator: ClassVar[str] = "between"
    noun: ClassVar[str] = "bounds"
    low: Bound | None
    high: Bound | None

    @property
    def call(self) -> str:
        return _bounds_call("between", repr(self.low), repr(self.high), self)

    def sentence(self) -> str | None:
        if self.low is not None and self.high is not None:
            return f"{shown(self.low)} to {shown(self.high)}."
        if self.low is not None:
            return f"At least {shown(self.low)}."
        return f"At most {shown(self.high)}."

    def problem(self, value: object) -> str | None:
        below = self.low is not None and _less(value, self.low)
        above = self.high is not None and _less(self.high, value)
        if not (below or above):
            return None
        if self.low is not None and self.high is not None:
            return f"isn't between {shown(self.low)} and {shown(self.high)}"
        if below:
            return f"is less than {shown(self.low)}"
        return f"is more than {shown(self.high)}"

    def misfit(self, base: object, name: str) -> str | None:
        if base not in _BOUNDED:
            return (
                f"{self.call} checks numbers, dates or times, "
                f"but parameter {name!r} has the type {describe(base)}."
            )
        for bound in (self.low, self.high):
            if bound is not None and not _bound_fits(bound, base):
                return (
                    f"{self.call} has {type(bound).__name__} bounds, but parameter "
                    f"{name!r} has the type {describe(base)}. "
                    f"Use {describe(base)} bounds."
                )
        return None


@dataclass(frozen=True)
class Length:
    decorator: ClassVar[str] = "length"
    noun: ClassVar[str] = "bounds"
    low: int | None
    high: int | None

    @property
    def call(self) -> str:
        return _bounds_call("length", str(self.low), str(self.high), self)

    def sentence(self) -> str | None:
        if self.low is not None and self.high is not None:
            return f"{self.low} to {self.high} characters."
        if self.low is not None:
            return f"At least {_characters(self.low)}."
        return f"At most {_characters(self.high)}."

    def problem(self, value: object) -> str | None:
        size = len(typing.cast("str", value))
        short = self.low is not None and size < self.low
        long = self.high is not None and size > self.high
        if not (short or long):
            return None
        if self.low is not None and self.high is not None:
            return f"isn't between {self.low} and {self.high} characters long"
        if short:
            return f"is shorter than {_characters(self.low)}"
        return f"is longer than {_characters(self.high)}"

    def misfit(self, base: object, name: str) -> str | None:
        return _text_misfit(self.call, base, name)


@dataclass(frozen=True)
class Matches:
    decorator: ClassVar[str] = "matches"
    noun: ClassVar[str] = "pattern"
    pattern: re.Pattern[str]

    @property
    def call(self) -> str:
        return f'@matches("{self.pattern.pattern}")'

    def sentence(self) -> str | None:
        return f"Must match {self.pattern.pattern}."

    def problem(self, value: object) -> str | None:
        if self.pattern.fullmatch(typing.cast("str", value)):
            return None
        return f"doesn't match {self.pattern.pattern}"

    def misfit(self, base: object, name: str) -> str | None:
        return _text_misfit(self.call, base, name)


@dataclass(frozen=True)
class Choices:
    decorator: ClassVar[str] = "choices"
    noun: ClassVar[str] = "choices"
    values: tuple[object, ...]
    call: str
    source: type[Enum] | None = None

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(shown(value) for value in self.values)

    def sentence(self) -> str | None:
        return None

    def problem(self, value: object) -> str | None:
        if value in self.values:
            return None
        return f"isn't one of {', '.join(self.labels)}"

    def misfit(self, base: object, name: str) -> str | None:
        source = self.source
        if source is not None:
            if base is source:
                return (
                    f"{self.call} allows every member of {source.__qualname__}, "
                    "which the annotation already does. Remove it."
                )
            return (
                f"{self.call} lists members of {source.__qualname__}, but parameter "
                f"{name!r} has the type {describe(base)}. "
                f"Annotate it as {source.__qualname__} instead."
            )
        for value in self.values:
            if typing.get_origin(base) is typing.Literal:
                literals: tuple[object, ...] = typing.get_args(base)
                if value not in literals:
                    allowed = ", ".join(repr(literal) for literal in literals)
                    return (
                        f"{self.call} lists {value!r}, but parameter {name!r} "
                        f"only takes {allowed}."
                    )
            elif not _value_fits(value, base):
                return (
                    f"{self.call} lists {value!r}, a {type(value).__name__}, but "
                    f"parameter {name!r} has the type {describe(base)}. "
                    f"Use {describe(base)} values."
                )
        return None


Child = Between | Length | Matches | Choices

CHILD_KINDS = (Between, Length, Matches, Choices)


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
                f"{found.call} mixes bound types. "
                "Use two numbers, two dates or two times."
            )
            raise TypeError(message)
        if _less(high, low):
            _wrong_way_round(found.call, Between(high, low).call)
    return _attach(found)


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
        _wrong_way_round(found.call, Length(high, low).call)
    return _attach(found)


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
    return _attach(Matches(compiled))


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
    return _attach(_choices(values))


def children_of(function: FunctionType) -> dict[str, tuple[Child, ...]]:
    attached: dict[str, list[Child]] = {}
    current: str | None = None
    for record in nodes_of(function):
        if isinstance(record, PARENT_KINDS):
            current = record.name
            _ = attached.setdefault(current, [])
        if isinstance(record, CHILD_KINDS):
            if current is None:
                message = (
                    f"{record.call} is above every parent, so it has nothing to "
                    "check. Put it right below the parent whose value it checks."
                )
                raise TypeError(message)
            attached[current].append(record)
    return {name: tuple(children) for name, children in attached.items()}


def first_problem(children: tuple[Child, ...], value: object) -> str | None:
    for child in children:
        problem = child.problem(value)
        if problem is not None:
            return problem
    return None


def _attach(child: Child) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        store(child, function, child.decorator)
        return function

    return decorate


def _choices(values: tuple[object, ...]) -> Choices:
    if len(values) == 1:
        only = values[0]
        _check_parentheses(only, "choices", "its values", '@choices("zip", "tar")')
        if isinstance(only, range):
            raise _range_error(only)
        if isinstance(only, type) and issubclass(only, Enum):
            return _checked_choices(tuple(only), f"@choices({only.__qualname__})", only)
        if isinstance(only, list | tuple | set | frozenset):
            items = tuple(typing.cast("Collection[object]", only))
            if isinstance(only, set | frozenset):
                items = tuple(sorted(items, key=shown))
            listed = ", ".join(_quoted(item) for item in items)
            return _checked_choices(items, f"@choices([{listed}])")
    call = f"@choices({', '.join(_quoted(value) for value in values)})"
    for value in values:
        if isinstance(value, list | tuple | set | frozenset | range) or (
            isinstance(value, type) and issubclass(value, Enum)
        ):
            message = (
                f"{call} mixes a collection with values. "
                "Pass the values one by one, or one collection."
            )
            raise TypeError(message)
    return _checked_choices(values, call)


def _checked_choices(
    values: tuple[object, ...], call: str, source: type[Enum] | None = None
) -> Choices:
    if not values:
        message = '@choices needs values, such as @choices("zip", "tar").'
        raise TypeError(message)
    for value in values:
        if values.count(value) > 1:
            message = f"{call} lists {value!r} twice. Remove one."
            raise ValueError(message)
    return Choices(values, call, source)


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


def _wrong_way_round(call: str, swapped: str) -> None:
    message = f"{call} has its bounds the wrong way round. Use {swapped}."
    raise ValueError(message)


def _bounds_call(decorator: str, low: str, high: str, child: Between | Length) -> str:
    if child.low is not None and child.high is not None:
        return f"@{decorator}({low}, {high})"
    if child.low is not None:
        return f"@{decorator}(low={low})"
    return f"@{decorator}(high={high})"


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


def _text_misfit(call: str, base: object, name: str) -> str | None:
    if base is str:
        return None
    return f"{call} checks text, but parameter {name!r} has the type {describe(base)}."


def _characters(count: int | None) -> str:
    return f"{count} character" if count == 1 else f"{count} characters"


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
