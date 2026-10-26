import inspect
import re
import typing
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from operator import itemgetter
from types import FunctionType
from typing import ClassVar, Protocol

from cliron._builtin_options import DEFAULT_BUILTINS, Builtins
from cliron._children import AnyChild, run_child
from cliron._conversion import NUMBER, Converter, describe, fits_value
from cliron._dependencies import Dependency, Given
from cliron._hooks import HookCall, first_handler
from cliron._names import closest, long_flag, token
from cliron._parents import Argument, Env, Parent, Stdin, call, flags

_FINAL_LINE_BREAK = re.compile(r"\r?\n\Z")
_LINE_BREAK = re.compile(r"\r?\n")


class MistakeError(Exception):
    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error: Exception = error


@dataclass(frozen=True)
class Input:
    parent: Parent
    converter: Converter | None
    default: object = None
    required: bool = False
    counted: bool = False
    children: tuple[AnyChild, ...] = ()
    accepts: object = None
    annotation: object = None
    handlers: tuple[HookCall, ...] = ()
    child_handlers: tuple[tuple[HookCall, ...], ...] = ()

    @property
    def name(self) -> str:
        return self.parent.name

    @property
    def display(self) -> str:
        return self.parent.label()

    @property
    def multiple(self) -> bool:
        return self.converter is not None and self.converter.collect is not None

    @property
    def default_items(self) -> tuple[object, ...]:
        if self.multiple:
            return tuple(typing.cast("Sequence[object]", self.default))
        return (self.default,)


class Definition:
    def __init__(
        self,
        inputs: Iterable[Input],
        dependencies: Iterable[Dependency] = (),
        injected: Mapping[str, type[object]] | None = None,
        hooks: Iterable[HookCall] = (),
        returns: object = None,
    ) -> None:
        self.inputs: tuple[Input, ...] = tuple(inputs)
        self.dependencies: tuple[Dependency, ...] = tuple(dependencies)
        self.injected: dict[str, type[object]] = dict(injected or {})
        self.hooks: tuple[HookCall, ...] = tuple(hooks)
        self.returns: object = returns
        self.labels: dict[str, str] = {
            target.name: target.display for target in self.inputs
        }
        self.env: frozenset[str] = frozenset(
            target.name for target in self.inputs if isinstance(target.parent, Env)
        )
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

    def builtins(self, inherited: Builtins) -> Builtins: ...


@dataclass(frozen=True)
class Request:
    kind: str
    nodes: list[Node]
    builtins: Builtins


@dataclass(frozen=True)
class Parsed:
    path: list[tuple[Node, dict[str, object]]]
    errors: list[Exception]
    builtins: Builtins
    request: Request | None = None


def node_path(nodes: Iterable[Node]) -> str:
    return " ".join(token(node.name) for node in nodes)


def parse(root: Node, args: Sequence[str]) -> Parsed:
    return _Reader(args).read(root)


class _Segment:
    def __init__(self, node: Node, inherited: Builtins, start: int) -> None:
        self.node: Node = node
        try:
            self.definition: Definition = node.definition()
            self.builtins: Builtins = node.builtins(inherited)
        except Exception as error:
            raise MistakeError(error) from error
        self.builtin_flags: dict[str, str] = self.builtins.flags
        self.start: int = start
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

    def given(self) -> Given:
        names = tuple(
            target.name
            for target in self.definition.inputs
            if target.name in self.raw or self.occurrences.get(target.name, 0)
        )
        return Given(names, self.definition.env)

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

    def resolve(self, target: Input, path: str) -> tuple[object, list[Exception]]:
        try:
            value, problems = self._read(target, path)
        except Exception as error:
            handler = _input_handler(target, error)
            if handler is None:
                raise
            return _parent_value(target, *handler, error, self.node), []
        if problems:
            handler = _input_handler(target, problems[0])
            if handler is not None:
                try:
                    return _parent_value(target, *handler, problems[0], self.node), []
                except (LookupError, ValueError) as raised:
                    return None, [raised, *problems[1:]]
        return value, problems

    def _read(self, target: Input, path: str) -> tuple[object, list[Exception]]:
        converter = target.converter
        if converter is None:
            return self._resolve_flag(target)
        unreadable = self._load(target)
        if unreadable is not None:
            return None, [unreadable]
        raw = self.raw.get(target.name)
        if raw is None:
            if target.required and target.name not in self.input_errors:
                return None, [LookupError(_missing(target, path))]
            return target.default, self._check_default(target)
        values: list[object] = []
        problems: list[Exception] = []
        for line, word in enumerate(raw, start=1):
            try:
                values.append(_value(target, converter, word, self.node))
            except ValueError as error:
                problems.append(ValueError(f"{_label(target, line)}: {error}"))
        if converter.collect is not None:
            return converter.collect(values), problems
        return (values[0] if values else None), problems

    def _resolve_flag(self, target: Input) -> tuple[object, list[Exception]]:
        count = self.occurrences.get(target.name, 0)
        value: object = count if target.counted else count > 0
        if not count:
            return value, self._check_default(target)
        try:
            value = _processed(target, value, self.node)
        except ValueError as error:
            return value, [ValueError(f"{target.display}: {error}")]
        return value, []

    def _check_default(self, target: Input) -> list[Exception]:
        runs = [
            index
            for index, found in enumerate(target.children)
            if found.default_check == "run"
        ]
        if not runs or target.default is None:
            return []
        checking = replace(
            target,
            children=tuple(target.children[index] for index in runs),
            child_handlers=tuple(target.child_handlers[index] for index in runs),
        )
        problems: list[Exception] = []
        for item in target.default_items:
            try:
                _ = _processed(checking, item, self.node)
            except ValueError as error:
                problems.append(ValueError(f"{target.display}: {error}"))
        return problems

    def _load(self, target: Input) -> Exception | None:
        try:
            text = typing.cast("object", target.parent.load())
        except UnicodeDecodeError as error:
            message = f"{target.display}: the input isn't valid {error.encoding} text."
            return ValueError(message)
        if text is None:
            return None
        if not isinstance(text, str):
            message = (
                f"{call(target.parent)} returned {type(text).__name__} from load(). "
                "Make it return str or None."
            )
            mistake = TypeError(message)
            mistake.add_note(location(self.node))
            raise MistakeError(mistake)
        self.raw[target.name] = _words(target, text)
        return None


class _Reader:
    def __init__(self, args: Sequence[str]) -> None:
        self.args: list[str] = list(args)
        self.position: int = 0
        self.options_ended: bool = False
        self.segments: list[_Segment] = []
        self.request: tuple[str, int] | None = None
        self.bare: tuple[int, Exception] | None = None

    def read(self, root: Node) -> Parsed:
        node: Node | None = root
        inherited = DEFAULT_BUILTINS
        while node is not None:
            segment = _Segment(node, inherited, self.position)
            self.segments.append(segment)
            self._read_segment(segment)
            node = self._read_command(segment)
            inherited = segment.builtins
        if self.request is not None:
            return self._answer(*self.request)
        self._report_unknown()
        parsed = self._resolve()
        if self.bare is not None and parsed.errors == [self.bare[1]]:
            return self._answer("usage", self.bare[0])
        return parsed

    def _answer(self, kind: str, index: int) -> Parsed:
        nodes = [segment.node for segment in self.segments[: index + 1]]
        builtins = self.segments[index].builtins
        return Parsed([], [], builtins, Request(kind, nodes, builtins))

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
        path = node_path(part.node for part in self.segments)
        if self.position == len(self.args):
            error = LookupError(f"'{path}' needs a command.")
            segment.word_errors.append((self.position, error))
            if segment.start == self.position and segment.builtins.help.flags:
                self.bare = (len(self.segments) - 1, error)
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
        if flag in segment.builtin_flags:
            self._read_builtin(segment, flag, start, given_value=bool(separator))
            return
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
            if flag in segment.builtin_flags:
                self._read_builtin(
                    segment, flag, start, given_value=rest.startswith("=")
                )
                if rest.startswith("="):
                    return
                continue
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

    def _read_builtin(
        self, segment: _Segment, flag: str, start: int, *, given_value: bool
    ) -> None:
        if given_value:
            segment.word_errors.append(
                (start, ValueError(f"{flag} doesn't take a value."))
            )
        else:
            self.request = (segment.builtin_flags[flag], len(self.segments) - 1)

    def _read_attached(
        self, segment: _Segment, target: Input, flag: str, rest: str
    ) -> None:
        if rest == "=":
            segment.report(target, _needs_value(target))
        elif rest.startswith("="):
            value = rest[1:]
            separate = (
                f"{long_flag(target.name)}={value}"
                if _is_option(value)
                else f"{flag} {value}"
            )
            message = f"Use {flag}{value} or {separate} instead of {flag}={value}."
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
                f"To pass {word!r}, write {long_flag(target.name)}={word}."
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
        for index, segment in enumerate(self.segments):
            segment.assign_arguments()
            command_path = node_path(part.node for part in self.segments[: index + 1])
            values: dict[str, object] = {}
            for target in segment.definition.inputs:
                values[target.name], problems = segment.resolve(target, command_path)
                errors.extend(segment.input_errors.get(target.name, []))
                errors.extend(problems)
            given = segment.given()
            label = segment.definition.labels.__getitem__
            errors.extend(
                ValueError(found.problem(given, label))
                for found in segment.definition.dependencies
                if not found.met(given)
            )
            errors.extend(
                error for _, error in sorted(segment.word_errors, key=itemgetter(0))
            )
            path.append((segment.node, values))
        return Parsed(path, errors, self.segments[-1].builtins)


def _is_option(word: str) -> bool:
    return word.startswith("-") and word != "-" and not NUMBER.fullmatch(word)


def _value(target: Input, converter: Converter, word: str, node: Node) -> object:
    return _processed(target, converter.convert(word), node)


def _processed(target: Input, value: object, node: Node) -> object:
    source = ""
    for found, handlers in zip(target.children, target.child_handlers, strict=True):
        source = f"@{found!r}"
        try:
            value = run_child(found, value)
        except Exception as error:
            handler = (
                None
                if isinstance(error, MistakeError)
                else first_handler(handlers, error)
            )
            if handler is None:
                raise
            value = _call_handler(*handler, error)
            source = f"hook function '{handler[0].hook.callback.__name__}'"
    if target.children and not fits_value(value, target.accepts):
        what = "None" if value is None else type(value).__name__
        expected = describe(target.accepts)
        message = (
            f"{source} returned {what}, but parameter "
            f"'{target.name}' has the type {expected}. Make it return {expected}."
        )
        error = TypeError(message)
        error.add_note(location(node))
        raise MistakeError(error)
    return value


def _input_handler(target: Input, error: Exception) -> tuple[HookCall, str] | None:
    if isinstance(error, MistakeError):
        return None
    return first_handler(target.handlers, error)


def _call_handler(handler: HookCall, parameter: str, error: Exception) -> object:
    return typing.cast("object", handler.hook.callback(**{parameter: error}))


def _parent_value(
    target: Input, handler: HookCall, parameter: str, error: Exception, node: Node
) -> object:
    value = _call_handler(handler, parameter, error)
    if fits_value(value, target.annotation):
        return value
    expected = describe(target.annotation)
    message = (
        f"hook function '{handler.hook.callback.__name__}' returned "
        f"{describe(type(value))}, but parameter '{target.name}' has the type "
        f"{expected}. Make it return {expected}."
    )
    mistake = TypeError(message)
    mistake.add_note(location(node))
    raise MistakeError(mistake) from None


def location(root: Node) -> str:
    original = typing.cast("object", inspect.unwrap(root.function))
    function = original if isinstance(original, FunctionType) else root.function
    code = typing.cast("FunctionType", function).__code__
    return (
        f"in {root.kind} '{token(root.name)}', "
        f"defined at {code.co_filename}:{code.co_firstlineno}"
    )


def _words(target: Input, text: str) -> list[str]:
    if not isinstance(target.parent, Stdin):
        return [text]
    text = _FINAL_LINE_BREAK.sub("", text, count=1)
    if not target.multiple:
        return [text]
    return _LINE_BREAK.split(text) if text else []


def _label(target: Input, line: int) -> str:
    if isinstance(target.parent, Stdin) and target.multiple:
        return f"{target.display}: line {line}"
    return target.display


def _missing(target: Input, path: str) -> str:
    message = target.parent.missing()
    if isinstance(target.parent, Stdin):
        return f"{message} For example: cat file.txt | {path}"
    return message


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
    match = closest(flag[2:], names)
    return None if match is None else names[match]


def _suggestion(word: str, candidates: Iterable[str]) -> str:
    match = closest(word, candidates)
    return "" if match is None else f" Did you mean {match!r}?"
