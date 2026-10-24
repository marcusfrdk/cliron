import inspect
import sys
import typing
from collections.abc import Callable
from types import FunctionType
from typing import ClassVar, NoReturn

from cliron._conversion import SUPPORTED, converter_for, describe
from cliron._names import check_name, is_parameter_name, parameter_suggestion, token
from cliron._parents import Argument, Flag, Parent, call, display, flags, parents_of
from cliron._parsing import Definition, Input, Node, parse

_UNSUPPORTED_KINDS = {
    inspect.Parameter.POSITIONAL_ONLY: (
        "parameter '{name}' is positional-only, but cliron passes every value "
        "by name. Remove the '/'."
    ),
    inspect.Parameter.VAR_POSITIONAL: (
        "parameter '*{name}' can't be filled from the command line. For several "
        'values, use {name}: list[str] with @{parent}("{name}").'
    ),
    inspect.Parameter.VAR_KEYWORD: (
        "parameter '**{name}' can't be filled from the command line. "
        "Give each input its own parameter."
    ),
}


class Root:
    """
    A command or a group of commands.

    Calling it runs the command line in ``sys.argv`` and exits.
    """

    kind: ClassVar[str]

    def __init__(self, name: str, function: Callable[..., object]) -> None:
        """
        Turn a function into a command or group.

        :param name: The name, in snake_case.
        :param function: The function to run.
        :raises TypeError: If ``function`` isn't a function, or a group has an
            argument.
        :raises ValueError: If two parents share a name or a short flag.
        """
        if not isinstance(function, FunctionType):
            message = f"@{self.kind} must decorate a function."
            raise TypeError(message)
        self.name: str = name
        self.function: FunctionType = function
        self.parents: tuple[Parent, ...] = parents_of(function)
        self.commands: dict[str, Command | Group] = {}
        self._definition: Definition | None = None
        self._check_parents()

    def __call__(self) -> NoReturn:
        """
        Run the command line in ``sys.argv`` and exit.

        :raises SystemExit: Always: with 0 on success and 2 for invalid input.
        """
        raise SystemExit(main(self, sys.argv[1:]))

    def definition(self) -> Definition:
        """
        Check the function and return its inputs, checking only once.

        :returns: The inputs, in the order their decorators are written.
        """
        if self._definition is None:
            self._definition = _define(self)
        return self._definition

    def _check_parents(self) -> None:
        names: dict[str, Parent] = {}
        typed: dict[str, Parent] = {}
        for parent in self.parents:
            if isinstance(parent, Argument) and self.kind == "group":
                message = (
                    f"group '{token(self.name)}' can't take arguments. "
                    f'Use @option("{parent.name}") instead.'
                )
                raise TypeError(message)
            other = names.setdefault(parent.name, parent)
            if other is not parent:
                message = (
                    f"parameter '{parent.name}' has two parents, "
                    f"{call(other)} and {call(parent)}."
                )
                raise ValueError(message)
            for key in flags(parent) or (display(parent),):
                other = typed.setdefault(key, parent)
                if other is not parent:
                    message = f"{key} is used by both {call(other)} and {call(parent)}."
                    raise ValueError(message)


class Command(Root):
    """A function that runs with values from the command line."""

    kind: ClassVar[str] = "command"


class Group(Root):
    """A group of commands, whose function runs before the command."""

    kind: ClassVar[str] = "group"

    def add(self, *nodes: "Command | Group") -> None:
        """
        Add commands and groups to the group, in the order given.

        :param nodes: The commands and groups to add.
        :raises TypeError: If a node isn't a command or a group.
        :raises ValueError: If the group already has a command with a node's
            name, or a node is this group or contains it.
        """
        for node in nodes:
            _check_node(self, node)
            key = token(node.name)
            if key in self.commands:
                message = f"group '{token(self.name)}' already has a command '{key}'."
                raise ValueError(message)
            self.commands[key] = node


def command(name: str) -> Callable[[Callable[..., object]], Command]:
    """
    Turn a function into a command.

    The ``argument``, ``option`` and ``flag`` decorators below this one fill
    the function's parameters from the command line, converted to the types of
    their annotations. What the function returns is printed: nothing for
    ``None``, a ``str`` as it is, and anything else as JSON.

    :param name: The command's name, in snake_case.
    :returns: A decorator that turns a function into the command.
    :raises TypeError: If ``name`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case.
    """
    checked = check_name(name, "command")

    def decorate(function: Callable[..., object]) -> Command:
        return Command(checked, function)

    return decorate


def group(name: str) -> Callable[[Callable[..., object]], Group]:
    """
    Turn a function into a group of commands.

    Put commands and groups in it with its ``add`` method. The group's
    function runs with its own options and flags before the command that was
    asked for, and must return ``None``.

    :param name: The group's name, in snake_case.
    :returns: A decorator that turns a function into the group.
    :raises TypeError: If ``name`` isn't a string.
    :raises ValueError: If ``name`` isn't snake_case.
    """
    checked = check_name(name, "group")

    def decorate(function: Callable[..., object]) -> Group:
        return Group(checked, function)

    return decorate


def _check_node(group: Group, node: object) -> None:
    if not isinstance(node, Root):
        message = (
            f"group '{token(group.name)}' can only add commands and groups, "
            f'not a {type(node).__name__}. Decorate it with @command("name") '
            'or @group("name") first.'
        )
        raise TypeError(message)
    if node is group:
        message = f"group '{token(group.name)}' can't be added to itself."
        raise ValueError(message)
    if isinstance(node, Group) and _contains(node, group):
        message = (
            f"group '{token(node.name)}' contains '{token(group.name)}', "
            "so it can't be added to it."
        )
        raise ValueError(message)


def _contains(group: Group, node: Root) -> bool:
    return any(
        child is node or (isinstance(child, Group) and _contains(child, node))
        for child in group.commands.values()
    )


def main(root: Node, args: list[str]) -> int:
    parsed = parse(root, args)
    if parsed.errors:
        for error in parsed.errors:
            _ = sys.stderr.write(f"error: {error}\n")
        return 2
    *groups, (leaf, values) = parsed.path
    for node, group_values in groups:
        result = node.function(**group_values)
        if result is not None:
            message = (
                f"group '{token(node.name)}' must return None, "
                f"but it returned a value of type {type(result).__name__}."
            )
            raise TypeError(message)
    _render(leaf, leaf.function(**values))
    return 0


def _render(node: Node, result: object) -> None:
    if result is None:
        return
    if isinstance(result, str):
        text = result
    else:
        import json

        try:
            text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            note = (
                f"command '{token(node.name)}' returned it. "
                "Return None, a str, or data that JSON can represent."
            )
            error.add_note(note)
            raise
    _ = sys.stdout.write(text + "\n")


def _define(root: Root) -> Definition:
    try:
        definition = Definition(_inputs(root))
        _check_arguments(definition.arguments)
    except Exception as error:
        original = typing.cast("object", inspect.unwrap(root.function))
        code = (
            original if isinstance(original, FunctionType) else root.function
        ).__code__
        note = (
            f"in {root.kind} '{token(root.name)}', "
            f"defined at {code.co_filename}:{code.co_firstlineno}"
        )
        error.add_note(note)
        raise
    return definition


def _inputs(root: Root) -> list[Input]:
    function = root.function
    if inspect.iscoroutinefunction(function) or inspect.isasyncgenfunction(function):
        message = (
            f"{function.__name__!r} is async, "
            "and cliron doesn't run async functions yet."
        )
        raise TypeError(message)
    if inspect.isgeneratorfunction(function):
        message = (
            f"{function.__name__!r} is a generator, "
            "and cliron doesn't run generator functions yet."
        )
        raise TypeError(message)
    parameters = inspect.signature(function).parameters
    hints: dict[str, object] = typing.get_type_hints(function, include_extras=True)
    for parameter in parameters.values():
        _check_parameter(root, parameter)
    return [
        _input(parent, parameters.get(parent.name), hints) for parent in root.parents
    ]


def _check_parameter(root: Root, parameter: inspect.Parameter) -> None:
    name = parameter.name
    if parameter.kind in _UNSUPPORTED_KINDS:
        parent = "option" if root.kind == "group" else "argument"
        message = _UNSUPPORTED_KINDS[parameter.kind].format(name=name, parent=parent)
        raise TypeError(message)
    if any(parent.name == name for parent in root.parents):
        return
    if name in {"self", "cls"} and _in_class(root.function):
        message = (
            f"parameter '{name}' has no parent. cliron calls plain functions, "
            "not methods, so define the function outside a class."
        )
    elif is_parameter_name(name):
        message = (
            f"parameter '{name}' has no parent. Add one above the function, "
            f'for example @option("{name}").'
        )
    else:
        suggestion = parameter_suggestion(name) or "a snake_case name"
        message = (
            f"parameter '{name}' has no parent, and a parent's name must be "
            f"snake_case. Rename the parameter to {suggestion}."
        )
    raise TypeError(message)


def _in_class(function: FunctionType) -> bool:
    outer = function.__qualname__.rpartition(".")[0]
    return outer != "" and not outer.endswith("<locals>")


def _input(
    parent: Parent, parameter: inspect.Parameter | None, hints: dict[str, object]
) -> Input:
    if parameter is None:
        message = (
            f"{call(parent)} has no parameter. Add {parent.name!r} to the function."
        )
        raise TypeError(message)
    if parent.name not in hints:
        message = f"parameter '{parent.name}' needs a type annotation."
        raise TypeError(message)
    annotation = hints[parent.name]
    default = typing.cast("object", parameter.default)
    if isinstance(parent, Flag):
        return _flag(parent, annotation, default)
    if annotation is bool:
        message = f"parameter '{parent.name}' is a bool. Use @flag(\"{parent.name}\")."
        raise TypeError(message)
    converter = converter_for(annotation)
    if converter is None:
        message = (
            f"parameter '{parent.name}' has the type {describe(annotation)}, "
            f"which cliron can't convert. Use {SUPPORTED}."
        )
        raise TypeError(message)
    required = default is inspect.Parameter.empty
    return Input(
        parent, converter, default=None if required else default, required=required
    )


def _flag(parent: Flag, annotation: object, default: object) -> Input:
    name = parent.name
    if annotation is bool:
        if default is False:
            return Input(parent, None, default=False)
        message = (
            f"flag '{name}' is off until passed, "
            f"so it must default to False: {name}: bool = False."
        )
        if default is True:
            message += (
                f' To turn something off, use @flag("no_{name}") '
                f"with no_{name}: bool = False."
            )
        raise ValueError(message)
    if annotation is int:
        if type(default) is int and default == 0:
            return Input(parent, None, default=0, counted=True)
        message = (
            f"flag '{name}' counts from 0, so it must default to 0: {name}: int = 0."
        )
        raise ValueError(message)
    message = (
        f"flag '{name}' has the type {describe(annotation)}, "
        "but a flag is a bool or an int."
    )
    raise TypeError(message)


def _check_arguments(arguments: tuple[Input, ...]) -> None:
    optional: Input | None = None
    for index, target in enumerate(arguments):
        if target.multiple and index < len(arguments) - 1:
            message = (
                f"argument '{target.name}' takes several values, "
                "so it must be the last argument."
            )
            raise TypeError(message)
        if target.required and optional is not None:
            message = (
                f"argument '{target.name}' has no default, so it can't come after "
                f"argument '{optional.name}', which has one."
            )
            raise TypeError(message)
        if not target.required:
            optional = target
