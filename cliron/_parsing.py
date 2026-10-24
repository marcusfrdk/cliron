from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from operator import itemgetter
from typing import ClassVar, Protocol

from cliron._conversion import NUMBER, Converter
from cliron._names import token
from cliron._parents import Argument, Parent, display, flags


@dataclass(frozen=True)
class Input:
    parent: Parent
    converter: Converter | None
    default: object = None
    required: bool = False
    counted: bool = False

    @property
    def name(self) -> str:
        return self.parent.name

    @property
    def display(self) -> str:
        return display(self.parent)

    @property
    def multiple(self) -> bool:
        return self.converter is not None and self.converter.collect is not None


class Definition:
    def __init__(self, inputs: Iterable[Input]) -> None:
        self.inputs: tuple[Input, ...] = tuple(inputs)
        self.options: dict[str, Input] = {
            flag: target for target in self.inputs for flag in flags(target.parent)
        }
        self.arguments: tuple[Input, ...] = tuple(
            target for target in self.inputs if isinstance(target.parent, Argument)
        )


class Node(Protocol):
    kind: ClassVar[str]

    @property
    def name(self) -> str: ...

    @property
    def function(self) -> Callable[..., object]: ...

    @property
    def commands(self) -> Mapping[str, "Node"]: ...

    def definition(self) -> Definition: ...


@dataclass(frozen=True)
class Parsed:
    path: list[tuple[Node, dict[str, object]]]
    errors: list[Exception]


def parse(root: Node, args: Sequence[str]) -> Parsed:
    return _Reader(args).read(root)


class _Segment:
    def __init__(self, node: Node) -> None:
        self.node: Node = node
        self.definition: Definition = node.definition()
        self.raw: dict[str, list[str]] = {}
        self.occurrences: dict[str, int] = {}
        self.words: list[tuple[int, str]] = []
        self.unknown: list[tuple[int, str]] = []
        self.input_errors: dict[str, list[Exception]] = {}
        self.word_errors: list[tuple[int, Exception]] = []

    def add(self, target: Input, value: str) -> None:
        self.raw.setdefault(target.name, []).append(value)

    def occur(self, target: Input) -> None:
        previous = self.occurrences.get(target.name, 0)
        if previous == 1 and not (target.multiple or target.counted):
            self.report(target, ValueError(f"{target.display} can only be given once."))
        self.occurrences[target.name] = previous + 1

    def report(self, target: Input, error: Exception) -> None:
        self.input_errors.setdefault(target.name, []).append(error)

    def assign_arguments(self) -> None:
        remaining = self.words
        for target in self.definition.arguments:
            count = len(remaining) if target.multiple else 1
            taken, remaining = remaining[:count], remaining[count:]
            if taken:
                self.raw[target.name] = [word for _, word in taken]
        for position, word in remaining:
            error = ValueError(f"unexpected argument {word!r}.")
            self.word_errors.append((position, error))

    def resolve(self, target: Input) -> tuple[object, list[Exception]]:
        converter = target.converter
        if converter is None:
            count = self.occurrences.get(target.name, 0)
            return (count if target.counted else count > 0), []
        raw = self.raw.get(target.name, [])
        if not raw:
            if target.required and target.name not in self.input_errors:
                return None, [LookupError(f"{target.display} is required.")]
            return target.default, []
        values: list[object] = []
        problems: list[Exception] = []
        for word in raw:
            try:
                values.append(converter.convert(word))
            except ValueError as error:
                problems.append(ValueError(f"{target.display}: {error}"))
        if converter.collect is not None:
            return converter.collect(values), problems
        return (values[0] if values else None), problems


class _Reader:
    def __init__(self, args: Sequence[str]) -> None:
        self.args: list[str] = list(args)
        self.position: int = 0
        self.options_ended: bool = False
        self.segments: list[_Segment] = []

    def read(self, root: Node) -> Parsed:
        node: Node | None = root
        while node is not None:
            segment = _Segment(node)
            self.segments.append(segment)
            self._read_segment(segment)
            node = self._read_command(segment)
        self._report_unknown()
        return self._resolve()

    def _read_segment(self, segment: _Segment) -> None:
        while self.position < len(self.args):
            start = self.position
            word = self.args[start]
            is_word = self.options_ended or not _is_option(word)
            if is_word and segment.node.kind == "group":
                return
            self.position += 1
            if is_word:
                segment.words.append((start, word))
            elif word == "--":
                self.options_ended = True
            elif word.startswith("--"):
                self._read_long(segment, word, start)
            else:
                self._read_short(segment, word, start)

    def _read_command(self, segment: _Segment) -> Node | None:
        if segment.node.kind != "group":
            return None
        commands = segment.node.commands
        path = " ".join(token(part.node.name) for part in self.segments)
        if self.position == len(self.args):
            error = LookupError(f"'{path}' needs a command.")
            segment.word_errors.append((self.position, error))
            return None
        start = self.position
        word = self.args[start]
        self.position += 1
        command = commands.get(word)
        if command is None:
            message = f"{word!r} isn't a {path} command.{_suggestion(word, commands)}"
            segment.word_errors.append((start, ValueError(message)))
        return command

    def _read_long(self, segment: _Segment, word: str, start: int) -> None:
        flag, separator, value = word.partition("=")
        target = segment.definition.options.get(flag)
        if target is None:
            if not separator and self._guess_takes_value(segment, flag, more=False):
                self._skip_value()
            segment.unknown.append((start, flag))
            return
        segment.occur(target)
        if target.converter is None:
            if separator:
                segment.report(target, _takes_no_value(target))
        elif separator:
            segment.add(target, value)
        else:
            self._read_value(segment, target)

    def _read_short(self, segment: _Segment, word: str, start: int) -> None:
        letters = word[1:]
        if not (letters[0].isascii() and letters[0].isalpha()):
            segment.unknown.append((start, word))
            return
        for index, letter in enumerate(letters):
            flag = f"-{letter}"
            rest = letters[index + 1 :]
            target = segment.definition.options.get(flag)
            if target is None:
                segment.unknown.append((start, flag))
                if rest.startswith("=") or self._guess_takes_value(
                    segment, flag, more=bool(rest)
                ):
                    if not rest:
                        self._skip_value()
                    return
                continue
            segment.occur(target)
            if target.converter is not None:
                self._read_attached(segment, target, flag, rest)
                return
            if rest.startswith("="):
                segment.report(target, _takes_no_value(target))
                return

    def _read_attached(
        self, segment: _Segment, target: Input, flag: str, rest: str
    ) -> None:
        if rest == "=":
            segment.report(target, _needs_value(target))
        elif rest.startswith("="):
            value = rest[1:]
            message = f"Use {flag}{value} or {flag} {value} instead of {flag}={value}."
            segment.report(target, ValueError(message))
        elif rest:
            segment.add(target, rest)
        else:
            self._read_value(segment, target)

    def _read_value(self, segment: _Segment, target: Input) -> None:
        if self.position == len(self.args):
            segment.report(target, _needs_value(target))
            return
        word = self.args[self.position]
        if _is_option(word):
            message = (
                f"{target.display} needs a value. "
                f"To pass {word!r}, write {target.display}={word}."
            )
            segment.report(target, LookupError(message))
            return
        self.position += 1
        segment.add(target, word)

    def _skip_value(self) -> None:
        if self.position < len(self.args) and not _is_option(self.args[self.position]):
            self.position += 1

    def _guess_takes_value(self, segment: _Segment, flag: str, *, more: bool) -> bool:
        for earlier in reversed(self.segments[:-1]):
            owner = earlier.definition.options.get(flag)
            if owner is not None:
                return owner.converter is not None
        match = _closest_flag(flag, segment.definition)
        if match is not None:
            return segment.definition.options[match].converter is not None
        if segment.node.kind != "group":
            return False
        return more or (
            self.position < len(self.args)
            and not _is_option(self.args[self.position])
            and self.args[self.position] not in segment.node.commands
        )

    def _report_unknown(self) -> None:
        for segment in self.segments:
            for position, flag in segment.unknown:
                owners = [
                    token(other.node.name)
                    for other in self.segments
                    if other is not segment and flag in other.definition.options
                ]
                error = ValueError(_unknown_option(flag, owners, segment.definition))
                segment.word_errors.append((position, error))

    def _resolve(self) -> Parsed:
        path: list[tuple[Node, dict[str, object]]] = []
        errors: list[Exception] = []
        for segment in self.segments:
            segment.assign_arguments()
            values: dict[str, object] = {}
            for target in segment.definition.inputs:
                values[target.name], problems = segment.resolve(target)
                errors.extend(segment.input_errors.get(target.name, []))
                errors.extend(problems)
            errors.extend(
                error for _, error in sorted(segment.word_errors, key=itemgetter(0))
            )
            path.append((segment.node, values))
        return Parsed(path, errors)


def _is_option(word: str) -> bool:
    return word.startswith("-") and word != "-" and not NUMBER.fullmatch(word)


def _needs_value(target: Input) -> LookupError:
    return LookupError(f"{target.display} needs a value.")


def _takes_no_value(target: Input) -> ValueError:
    return ValueError(f"{target.display} doesn't take a value.")


def _unknown_option(flag: str, owners: list[str], definition: Definition) -> str:
    if len(owners) == 1:
        return f"{flag} belongs to '{owners[0]}'. Write it right after '{owners[0]}'."
    if owners:
        names = " and ".join(f"'{owner}'" for owner in owners)
        return f"{flag} belongs to {names}. Write it right after the one you mean."
    match = _closest_flag(flag, definition)
    suggestion = "" if match is None else f" Did you mean '{match}'?"
    return f"unknown option '{flag}'.{suggestion}"


def _closest_flag(flag: str, definition: Definition) -> str | None:
    if not flag.startswith("--"):
        return None
    names = {
        option[2:]: option for option in definition.options if option.startswith("--")
    }
    match = _closest(flag[2:], names)
    return None if match is None else names[match]


def _suggestion(word: str, candidates: Iterable[str]) -> str:
    match = _closest(word, candidates)
    return "" if match is None else f" Did you mean {match!r}?"


def _closest(word: str, candidates: Iterable[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(word, list(candidates), n=1)
    return matches[0] if matches else None
