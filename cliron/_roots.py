import inspect
import sys
import typing
from collections.abc import Callable, Sequence
from types import FunctionType
from typing import ClassVar, NoReturn

from cliron._builtin_options import (
    Builtins,
    HelpOption,
    VersionOption,
    help_option_for,
    version_option_for,
)
from cliron._conversion import SUPPORTED, converter_for, describe
from cliron._help import render_help, terminal_width, usage_hint
from cliron._names import check_name, is_parameter_name, parameter_suggestion, token
from cliron._parents import (
    Argument,
    Env,
    Flag,
    Parent,
    call,
    display,
    flags,
    parents_of,
)
from cliron._parsing import Definition, Input, Node, Request, parse
from cliron._signals import finish

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

    def __init__(
        self,
        name: str,
        function: Callable[..., object],
        help_option: HelpOption | None = None,
        version_option: VersionOption | None = None,
    ) -> None:
        """
        Turn a function into a command or group.

        :param name: The name, in snake_case.
        :param function: The function to run.
        :param help_option: The help flags, or ``None`` to inherit them.
        :param version_option: The version, or ``None`` to inherit it.
        :raises TypeError: If ``function`` isn't a function, or a group has an
            argument.
        :raises ValueError: If two parents share a name, a flag or an
            environment variable.
        """
        if not isinstance(function, FunctionType):
            message = f"@{self.kind} must decorate a function."
            raise TypeError(message)
        self.name: str = name
        self.function: FunctionType = function
        self.parents: tuple[Parent, ...] = parents_of(function)
        self.help_option: HelpOption | None = help_option
        self.version_option: VersionOption | None = version_option
        self.commands: dict[str, Command | Group] = {}
        self._definition: Definition | None = None
        self._check_parents()

    def __call__(self) -> NoReturn:
        """
        Run the command line in ``sys.argv`` and exit.

        Ctrl+C ends the program without a traceback. SIGTERM, and Ctrl+Break on
        Windows, raise ``SystemExit(143)`` so that cleanup runs, unless the
        program already handles or ignores them. On Linux and macOS, output that
        a closed pipe can no longer take ends the program quietly with 1.

        :raises SystemExit: With 0 on success, 2 for invalid input, 143 for
            SIGTERM and 1 for a closed pipe.
        :raises KeyboardInterrupt: For Ctrl+C, which Python turns into its usual
            exit status, without printing a traceback.
        """
        finish(lambda: main(self, sys.argv[1:]))

    def definition(self) -> Definition:
        """
        Check the function and return its inputs, checking only once.

        :returns: The inputs, in the order their decorators are written.
        """
        if self._definition is None:
            self._definition = _define(self)
        return self._definition

    def builtins(self, inherited: Builtins) -> Builtins:
        """
        Combine the built-in options this node declares with those it inherits.

        :param inherited: The built-in options of the group above, or the
            defaults at the top of the command line.
        :returns: The node's help and version options.
        :raises ValueError: If one of their flags is also one of the node's
            options, or help and version share a flag.
        """
        builtins = Builtins(
            self.help_option or inherited.help,
            self.version_option or inherited.version,
        )
        definition = self.definition()
        try:
            _check_builtin_flags(definition, builtins)
        except ValueError as error:
            error.add_note(_location(self))
            raise
        return builtins

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


def command(
    name: str,
    *,
    help_flags: bool | Sequence[str] = True,
    version: str | None = None,
) -> Callable[[Callable[..., object]], Command]:
    """
    Turn a function into a command.

    The ``argument``, ``option``, ``flag`` and ``env`` decorators below this
    one fill the function's parameters from the command line and the
    environment, converted to the types of their annotations. What the function
    returns is printed: nothing for ``None``, a ``str`` as it is, and anything
    else as JSON.

    :param name: The command's name, in snake_case.
    :param help_flags: The flags that show help. ``True`` takes the enclosing
        group's, or ``-h`` and ``--help`` at the top. ``False`` or an empty list
        turns help off.
    :param version: A version that ``--version`` prints, such as ``"1.4.0"``.
        ``None`` takes the enclosing group's.
    :returns: A decorator that turns a function into the command.
    :raises TypeError: If ``name`` or ``version`` isn't a string, or
        ``help_flags`` isn't a bool or a list of strings.
    :raises ValueError: If ``name`` isn't snake_case, or a help flag isn't a
        short or long flag or is listed twice.
    """
    checked = check_name(name, "command")
    help_option = help_option_for(help_flags, "command")
    version_option = version_option_for(version, "command")

    def decorate(function: Callable[..., object]) -> Command:
        return Command(checked, function, help_option, version_option)

    return decorate


def group(
    name: str,
    *,
    help_flags: bool | Sequence[str] = True,
    version: str | None = None,
) -> Callable[[Callable[..., object]], Group]:
    """
    Turn a function into a group of commands.

    Put commands and groups in it with its ``add`` method. The group's
    function runs with its own options, flags and environment variables before
    the command that was asked for, and must return ``None``.

    :param name: The group's name, in snake_case.
    :param help_flags: The flags that show help, for the group and everything
        in it that doesn't choose its own. ``True`` takes the enclosing group's,
        or ``-h`` and ``--help`` at the top. ``False`` or an empty list turns
        help off.
    :param version: A version that ``--version`` prints, for the group and
        everything in it, such as ``"1.4.0"``. ``None`` takes the enclosing
        group's.
    :returns: A decorator that turns a function into the group.
    :raises TypeError: If ``name`` or ``version`` isn't a string, or
        ``help_flags`` isn't a bool or a list of strings.
    :raises ValueError: If ``name`` isn't snake_case, or a help flag isn't a
        short or long flag or is listed twice.
    """
    checked = check_name(name, "group")
    help_option = help_option_for(help_flags, "group")
    version_option = version_option_for(version, "group")

    def decorate(function: Callable[..., object]) -> Group:
        return Group(checked, function, help_option, version_option)

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
    request = parsed.request
    if request is not None:
        return _answer(request)
    if parsed.errors:
        for error in parsed.errors:
            _ = sys.stderr.write(f"error: {error}\n")
        nodes = [node for node, _ in parsed.path]
        hint = usage_hint(nodes, parsed.builtins)
        if hint is not None:
            _ = sys.stderr.write(hint + "\n")
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


def _answer(request: Request) -> int:
    if request.kind == "version" and request.builtins.version is not None:
        name = token(request.nodes[0].name)
        _ = sys.stdout.write(f"{name} {request.builtins.version.version}\n")
        return 0
    stream = sys.stdout if request.kind == "help" else sys.stderr
    help_text = render_help(request.nodes, request.builtins, terminal_width(stream))
    _ = stream.write(help_text)
    return 0 if request.kind == "help" else 2


def _check_builtin_flags(definition: Definition, builtins: Builtins) -> None:
    version_option = builtins.version
    if version_option is not None:
        for flag in set(builtins.help.flags) & set(version_option.flags):
            message = (
                f"{flag} is used by both help_flags and version. "
                f"Leave {flag} out of help_flags."
            )
            raise ValueError(message)
    for flag, kind in builtins.flags.items():
        target = definition.options.get(flag)
        if target is not None:
            fix = (
                ", or choose other help_flags" if kind == "help" else " for the option"
            )
            message = (
                f"{flag} is used by both {call(target.parent)} and {kind}. "
                f"Use another flag{fix}."
            )
            raise ValueError(message)


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
        error.add_note(_location(root))
        raise
    return definition


def _location(root: Root) -> str:
    original = typing.cast("object", inspect.unwrap(root.function))
    code = (original if isinstance(original, FunctionType) else root.function).__code__
    return (
        f"in {root.kind} '{token(root.name)}', "
        f"defined at {code.co_filename}:{code.co_firstlineno}"
    )


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
        if isinstance(parent, Env):
            message = (
                f"parameter '{parent.name}' is a bool, which only @flag can fill. "
                "For an environment variable, use an int, such as "
                f"{parent.name}: int = 0, which {parent.variable}=1 sets to 1."
            )
        else:
            message = (
                f"parameter '{parent.name}' is a bool. Use @flag(\"{parent.name}\")."
            )
        raise TypeError(message)
    converter = converter_for(annotation)
    if converter is None:
        message = (
            f"parameter '{parent.name}' has the type {describe(annotation)}, "
            f"which cliron can't convert. Use {SUPPORTED}."
        )
        raise TypeError(message)
    if isinstance(parent, Env) and converter.collect is not None:
        message = (
            f"parameter '{parent.name}' has the type {describe(annotation)}, "
            f"but {call(parent)} reads one value. Use a type without list or tuple."
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
