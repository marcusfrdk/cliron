import math
import re
import sys
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import NoneType, UnionType

from cliron._names import token

_INTEGER = re.compile(r"[+-]?[0-9]+")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

_SPECIAL_FORM_UNION: object = typing.get_origin(typing.Literal[""] | None)

SUPPORTED = (
    "str, int, float, Path, date, datetime, time, an Enum, a Literal of strings, "
    "X | None, list[X] and tuple[X, ...]"
)


@dataclass(frozen=True)
class Converter:
    convert: Callable[[str], object]
    metavar: str
    collect: Callable[[list[object]], object] | None = None
    choices: tuple[str, ...] = ()


def converter_for(annotation: object) -> Converter | None:
    origin: object = typing.get_origin(annotation)
    arguments: tuple[object, ...] = typing.get_args(annotation)
    if _is_union(origin):
        values = [argument for argument in arguments if argument is not NoneType]
        return converter_for(values[0]) if len(values) == 1 else None
    if origin is list and len(arguments) == 1:
        return _collection(arguments[0], list)
    if origin is tuple and arguments[1:] == (Ellipsis,):
        return _collection(arguments[0], tuple)
    return _scalar(annotation)


def describe(annotation: object) -> str:
    if annotation is NoneType:
        return "None"
    if isinstance(annotation, type):
        return annotation.__qualname__
    return repr(annotation)


def union_members(annotation: object) -> tuple[object, ...]:
    if _is_union(typing.get_origin(annotation)):
        return typing.cast("tuple[object, ...]", typing.get_args(annotation))
    return (annotation,)


def _is_union(origin: object) -> bool:
    return origin is UnionType or origin is _SPECIAL_FORM_UNION


def _collection(
    annotation: object, collect: Callable[[list[object]], object]
) -> Converter | None:
    converter = _scalar(annotation)
    return None if converter is None else replace(converter, collect=collect)


def _scalar(annotation: object) -> Converter | None:
    if isinstance(annotation, type):
        if annotation in _SCALARS:
            return _SCALARS[annotation]
        if issubclass(annotation, Enum):
            return _choices(_members(annotation))
    if typing.get_origin(annotation) is typing.Literal:
        values: tuple[object, ...] = typing.get_args(annotation)
        strings = [value for value in values if isinstance(value, str)]
        if len(strings) == len(values):
            return _choices({string: string for string in strings})
    return None


def text_converter(annotation: object, known: Converter | None) -> Converter:
    base = value_type(annotation)
    if known is not None:
        metavar = known.metavar
    elif isinstance(base, type):
        metavar = base.__name__.upper()
    else:
        metavar = "VALUE"
    return Converter(_to_str, metavar, _collector(annotation))


def _collector(annotation: object) -> Callable[[list[object]], object] | None:
    origin: object = typing.get_origin(annotation)
    arguments: tuple[object, ...] = typing.get_args(annotation)
    if _is_union(origin):
        return _collector(next(item for item in arguments if item is not NoneType))
    if origin is list:
        return list
    if origin is tuple:
        return tuple
    return None


def fits_value(value: object, annotation: object) -> bool:
    origin: object = typing.get_origin(annotation)
    arguments: tuple[object, ...] = typing.get_args(annotation)
    if _is_union(origin):
        return any(fits_value(value, item) for item in arguments)
    if origin is typing.Literal:
        return value in arguments
    if not isinstance(annotation, type):
        return True
    if isinstance(value, bool) and annotation is not bool:
        return False
    if annotation is float:
        return isinstance(value, int | float)
    return isinstance(value, annotation)


def value_type(annotation: object) -> object:
    origin: object = typing.get_origin(annotation)
    arguments: tuple[object, ...] = typing.get_args(annotation)
    if _is_union(origin):
        return value_type(next(item for item in arguments if item is not NoneType))
    if origin is list or origin is tuple:
        return arguments[0]
    return annotation


def shown(value: object) -> str:
    if isinstance(value, Enum):
        return typed_member(value)
    if isinstance(value, str) and (
        not value or not value.isprintable() or value != value.strip()
    ):
        return repr(value)
    return str(value)


def typed_member(member: Enum) -> str:
    return token(member.name.lower())


def _members(enum: type[Enum]) -> dict[str, Enum]:
    members: dict[str, Enum] = {}
    for member in enum:
        key = typed_member(member)
        other = members.setdefault(key, member)
        if other is not member:
            message = (
                f"{enum.__qualname__}.{other.name} and {enum.__qualname__}."
                f"{member.name} would both be typed {key!r}. Rename one of them."
            )
            raise TypeError(message)
    if not members:
        message = f"{enum.__qualname__} has no members to choose from. Add one."
        raise TypeError(message)
    return members


def _to_str(value: str) -> str:
    return value


def _to_int(value: str) -> int:
    if not _INTEGER.fullmatch(value):
        message = f"{value!r} isn't a whole number."
        raise ValueError(message)
    try:
        return int(value)
    except ValueError:
        message = (
            "a whole number can't have more than "
            f"{sys.get_int_max_str_digits()} digits."
        )
        raise ValueError(message) from None


def _to_float(value: str) -> float:
    if not NUMBER.fullmatch(value):
        message = f"{value!r} isn't a number."
        raise ValueError(message)
    number = float(value)
    if not math.isfinite(number):
        message = f"{value!r} is out of range."
        raise ValueError(message)
    return number


def _to_path(value: str) -> Path:
    if value:
        return Path(value)
    message = "a path can't be empty."
    raise ValueError(message)


def _from_iso(
    parse: Callable[[str], object], description: str, metavar: str
) -> Converter:
    def convert(value: str) -> object:
        try:
            return parse(value)
        except ValueError:
            message = f"{value!r} isn't {description}."
            raise ValueError(message) from None

    return Converter(convert, metavar)


def _choices(choices: Mapping[str, object]) -> Converter:
    def convert(value: str) -> object:
        if value in choices:
            return choices[value]
        message = f"{value!r} isn't one of {', '.join(choices)}."
        raise ValueError(message)

    return Converter(convert, f"[{'|'.join(choices)}]", choices=tuple(choices))


_SCALARS: dict[type, Converter] = {
    str: Converter(_to_str, "TEXT"),
    int: Converter(_to_int, "INT"),
    float: Converter(_to_float, "FLOAT"),
    Path: Converter(_to_path, "PATH"),
    date: _from_iso(date.fromisoformat, "a date (YYYY-MM-DD)", "DATE"),
    datetime: _from_iso(
        datetime.fromisoformat, "a date and time (YYYY-MM-DD HH:MM)", "DATETIME"
    ),
    time: _from_iso(time.fromisoformat, "a time (HH:MM or HH:MM:SS)", "TIME"),
}
