import inspect
import sys
import typing
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import FunctionType, MappingProxyType, NoneType
from typing import ClassVar, NoReturn

from cliron._builtin_options import (
    Builtins,
    HelpOption,
    VersionOption,
    help_option_for,
    version_option_for,
)
from cliron._children import (
    AnyChild,
    Choices,
    check_below,
    checks_on_run,
    child_function,
    converts,
    misfit,
    run_child,
)
from cliron._completion import completion_script
from cliron._context import Context, injected
from cliron._conversion import (
    SUPPORTED,
    converter_for,
    describe,
    fits_value,
    text_converter,
    union_members,
    value_type,
)
from cliron._dependencies import Dependency, cycle_problem, dependencies_for
from cliron._help import render_help, terminal_width, usage_hint
from cliron._hooks import Attached, EventName, Hook, HookCall, first_handler, hooks_of
from cliron._names import (
    check_aliases,
    check_name,
    closest,
    is_parameter_name,
    parameter_suggestion,
    token,
)
from cliron._nodes import is_async, settled
from cliron._parents import (
    Argument,
    CommandLineParent,
    Env,
    Flag,
    Parent,
    Stdin,
    call,
    children_of,
    flags,
    load_function,
    parents_of,
)
from cliron._parsing import (
    Definition,
    Input,
    MistakeError,
    Node,
    Reader,
    Request,
    location,
)
from cliron._signals import finish, run_in_loop

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


@dataclass(frozen=True)
class Settings:
    aliases: tuple[str, ...]
    help_option: HelpOption | None
    version_option: VersionOption | None
    dependencies: tuple[Dependency, ...]


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
        settings: Settings,
    ) -> None:
        """
        Turn a function into a command or group.

        :param name: The name, in snake_case.
        :param function: The function to run.
        :param settings: The aliases, the help flags and version, or ``None`` to
            inherit them, and the dependencies between the inputs.
        :raises TypeError: If ``function`` isn't a function, or a group has an
            argument or reads stdin.
        :raises ValueError: If two parents share a name, a flag or an
            environment variable, a command reads stdin twice, or a dependency
            names an input the function doesn't have.
        """
        check_below(function, self.kind)
        if not isinstance(function, FunctionType):
            message = (
                f"@{self.kind} must decorate a function. Put it directly above a def."
            )
            raise TypeError(message)
        self.name: str = name
        self.aliases: tuple[str, ...] = settings.aliases
        self.function: FunctionType = function
        self.parents: tuple[Parent, ...] = parents_of(function)
        self.children: dict[str, tuple[AnyChild, ...]] = children_of(function)
        self.attached: Attached = hooks_of(function)
        self.hooks: tuple[Hook, ...] = self.attached.root
        self.help_option: HelpOption | None = settings.help_option
        self.version_option: VersionOption | None = settings.version_option
        self.dependencies: tuple[Dependency, ...] = settings.dependencies
        self.commands: dict[str, Command | Group] = {}
        self.names: dict[str, Command | Group] = {}
        self._definition: Definition | None = None
        self._check_parents()
        self._check_dependency_names()

    def __call__(self) -> NoReturn:
        """
        Run the command line in ``sys.argv`` and exit.

        Ctrl+C ends the program without a traceback. SIGTERM, and Ctrl+Break on
        Windows, raise ``SystemExit(143)`` so that cleanup runs, unless the
        program already handles or ignores them. On Linux and macOS, output that
        a closed pipe can no longer take ends the program quietly with 1.

        A mistake in the CLI's definition that the run finds is printed with
        where it was made, instead of a traceback.

        :raises SystemExit: With 0 on success, 2 for invalid input, 143 for
            SIGTERM, and 1 for a closed pipe or a mistake in the definition.
        :raises KeyboardInterrupt: For Ctrl+C, which Python turns into its usual
            exit status, without printing a traceback.
        """
        finish(lambda: _main_or_mistake(self, sys.argv[1:]))

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
            error.add_note(location(self))
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
            if isinstance(parent, Stdin) and self.kind == "group":
                message = (
                    f"group '{token(self.name)}' can't read stdin. "
                    f'Use @stdin("{parent.name}") on a command.'
                )
                raise TypeError(message)
            other = names.setdefault(parent.name, parent)
            if other is not parent:
                message = (
                    f"parameter '{parent.name}' has two parents, "
                    f"{call(other)} and {call(parent)}. Remove one."
                )
                raise ValueError(message)
            for key in flags(parent) or (parent.label(),):
                other = typed.setdefault(key, parent)
                if other is not parent:
                    message = (
                        f"{key} is used by both {call(other)} and {call(parent)}. "
                        f"{_clash_fix(key)}"
                    )
                    raise ValueError(message)

    def _check_dependency_names(self) -> None:
        names = [parent.name for parent in self.parents]
        for found in self.dependencies:
            for name in found.names:
                if name not in names:
                    match = closest(name, names)
                    suggestion = "" if match is None else f" Did you mean {match!r}?"
                    message = (
                        f"{found.call} names {name!r}, which isn't an input of "
                        f"{self.kind} '{token(self.name)}'.{suggestion}"
                    )
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
        :raises ValueError: If a node's name or one of its aliases is already a
            name or alias in the group, or a node is this group or contains it.
        """
        for node in nodes:
            _check_node(self, node)
            _check_names(self, node)
            self.commands[token(node.name)] = node
            for name in (node.name, *node.aliases):
                self.names[token(name)] = node


def command(
    name: str,
    *,
    aliases: str | Sequence[str] = (),
    help_flags: bool | Sequence[str] = True,
    version: str | None = None,
    dependencies: Sequence[Dependency] = (),
) -> Callable[[Callable[..., object]], Command]:
    """
    Turn a function into a command.

    The ``argument``, ``option``, ``flag``, ``env`` and ``stdin`` decorators
    below this one fill the function's parameters from the command line, the
    environment and piped input, converted to the types of their annotations.
    What the function returns is printed: nothing for ``None``, a ``str`` as it
    is, and anything else as JSON.

    :param name: The command's name, in snake_case.
    :param aliases: Other names that run the command, in snake_case, such as
        ``"ls"`` or ``["ls", "l"]``. Help lists them next to the name.
    :param help_flags: The flags that show help. ``True`` takes the enclosing
        group's, or ``-h`` and ``--help`` at the top. ``False`` or an empty list
        turns help off.
    :param version: A version that ``--version`` prints, such as ``"1.4.0"``.
        ``None`` takes the enclosing group's.
    :param dependencies: Dependencies between the inputs, such as
        ``[dependency.together("user", "password")]``, checked after the inputs
        are read.
    :returns: A decorator that turns a function into the command.
    :raises TypeError: If ``name`` or ``version`` isn't a string, ``aliases``
        isn't a string or a list of strings, ``help_flags`` isn't a bool or a
        list of strings, or ``dependencies`` isn't a list of dependencies.
    :raises ValueError: If ``name`` or an alias isn't snake_case, an alias is
        the name or is listed twice, or a help flag isn't a short or long flag
        or is listed twice.
    """
    checked = check_name(name, "command")
    settings = Settings(
        check_aliases(aliases, checked, "command"),
        help_option_for(help_flags, "command"),
        version_option_for(version, "command"),
        dependencies_for(dependencies, "command"),
    )

    def decorate(function: Callable[..., object]) -> Command:
        return Command(checked, function, settings)

    return decorate


def group(
    name: str,
    *,
    aliases: str | Sequence[str] = (),
    help_flags: bool | Sequence[str] = True,
    version: str | None = None,
    dependencies: Sequence[Dependency] = (),
) -> Callable[[Callable[..., object]], Group]:
    """
    Turn a function into a group of commands.

    Put commands and groups in it with its ``add`` method. The group's
    function runs with its own options, flags and environment variables before
    the command that was asked for, and must return ``None``. A function that
    yields once runs the code after its ``yield`` once the command and the
    groups inside have finished, and on failure the exception is raised at the
    ``yield``, so ``try`` and ``finally`` around it work as usual.

    :param name: The group's name, in snake_case.
    :param aliases: Other names that run the group, in snake_case, such as
        ``"t"`` or ``["t", "tg"]``. Help lists them next to the name.
    :param help_flags: The flags that show help, for the group and everything
        in it that doesn't choose its own. ``True`` takes the enclosing group's,
        or ``-h`` and ``--help`` at the top. ``False`` or an empty list turns
        help off.
    :param version: A version that ``--version`` prints, for the group and
        everything in it, such as ``"1.4.0"``. ``None`` takes the enclosing
        group's.
    :param dependencies: Dependencies between the group's own inputs, such as
        ``[dependency.together("user", "password")]``, checked after the inputs
        are read.
    :returns: A decorator that turns a function into the group.
    :raises TypeError: If ``name`` or ``version`` isn't a string, ``aliases``
        isn't a string or a list of strings, ``help_flags`` isn't a bool or a
        list of strings, or ``dependencies`` isn't a list of dependencies.
    :raises ValueError: If ``name`` or an alias isn't snake_case, an alias is
        the name or is listed twice, or a help flag isn't a short or long flag
        or is listed twice.
    """
    checked = check_name(name, "group")
    settings = Settings(
        check_aliases(aliases, checked, "group"),
        help_option_for(help_flags, "group"),
        version_option_for(version, "group"),
        dependencies_for(dependencies, "group"),
    )

    def decorate(function: Callable[..., object]) -> Group:
        return Group(checked, function, settings)

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


def _check_names(group: Group, node: Root) -> None:
    for name in (node.name, *node.aliases):
        word = token(name)
        other = group.names.get(word)
        if other is not None:
            raise ValueError(_clash(group, node, word, other))


def _clash(group: Group, node: Root, word: str, other: Root) -> str:
    owner = token(other.name)
    if owner == word:
        taken = f"already has a command '{word}'"
        fixes = ("Rename one of them.", "Remove the alias or rename the command.")
    else:
        taken = f"already uses '{word}' as an alias of '{owner}'"
        fixes = ("Rename one of them or remove the alias.", "Remove one of them.")
    start = f"group '{token(group.name)}' {taken}"
    if token(node.name) == word:
        return f"{start}. {fixes[0]}"
    return f"{start}, so it can't be an alias of '{token(node.name)}'. {fixes[1]}"


def _contains(group: Group, node: Root) -> bool:
    return any(
        child is node or (isinstance(child, Group) and _contains(child, node))
        for child in group.commands.values()
    )


def _main_or_mistake(root: Root, args: list[str]) -> int:
    try:
        return main(root, args)
    except MistakeError as mistake:
        notes = typing.cast("list[str]", getattr(mistake.error, "__notes__", []))
        lines = [f"error: {mistake.error}", *(f"  {note}" for note in notes)]
        _ = sys.stderr.write("".join(f"{line}\n" for line in lines))
        return 1


def main(root: Node, args: list[str]) -> int:
    reader = Reader(args)
    request = reader.read(root)
    if request is not None:
        return _answer(request)
    return _drive(_complete(reader), needs_loop=_needs_loop(reader.nodes))


async def _complete(reader: Reader) -> int:
    parsed = await reader.resolve()
    if parsed.request is not None:
        return _answer(parsed.request)
    if parsed.errors:
        for error in parsed.errors:
            _ = sys.stderr.write(f"error: {error}\n")
        nodes = [node for node, _ in parsed.path]
        hint = usage_hint(nodes, parsed.builtins)
        if hint is not None:
            _ = sys.stderr.write(hint + "\n")
        return 2
    context = Context(
        tuple(token(node.name) for node, _ in parsed.path),
        tuple(MappingProxyType(dict(values)) for _, values in parsed.path),
    )
    output = await _run_span(parsed.path, {Context: context})
    _render(parsed.path[-1][0], output)
    return 0


def _needs_loop(nodes: list[Node]) -> bool:
    return any(is_async(function) for node in nodes for function in _functions(node))


def _functions(node: Node) -> list[object]:
    definition = node.definition()
    found: list[object] = [node.function]
    found.extend(each.hook.callback for each in definition.hooks)
    for target in definition.inputs:
        found.append(load_function(target.parent))
        found.extend(child_function(each) for each in target.children)
        found.extend(each.hook.callback for each in target.handlers)
        found.extend(
            each.hook.callback
            for handlers in target.child_handlers
            for each in handlers
        )
    return found


def _drive(coroutine: Coroutine[object, None, int], *, needs_loop: bool) -> int:
    if needs_loop:
        return run_in_loop(coroutine)
    try:
        _ = coroutine.send(None)
    except StopIteration as done:
        return typing.cast("int", done.value)
    coroutine.close()
    message = (
        "something on this command line returned a value to await that waits "
        "for an event loop, but no function, hook, child or parent on it is "
        "async def. Make the one that waits async def."
    )
    raise RuntimeError(message)


Teardown = Generator[object, None, object] | AsyncGenerator[object, None]
Shared = dict[type[object], object]


async def _run_span(
    path: list[tuple[Node, dict[str, object]]], shared: Shared
) -> object:
    (node, values), *inside = path
    entered = False
    try:
        try:
            await _run_hooks(node, "start", shared)
            entered = True
            arguments = {**values, **_arguments(node.definition().injected, shared)}
            if inside:
                output = await _run_around(node, arguments, inside, shared)
            else:
                output = await settled(node.function(**arguments))
        except Exception as error:
            handler = _handler_for(node, error)
            if handler is None:
                raise
            output = await _handle(node, *handler, error, shared)
        await _run_hooks(node, "success", shared)
    finally:
        if entered:
            await _run_hooks(node, "exit", shared)
    return output


def _handler_for(node: Node, error: Exception) -> tuple[HookCall, str] | None:
    if isinstance(error, MistakeError):
        return None
    return first_handler(node.definition().hooks, error)


async def _handle(
    node: Node, handler: HookCall, parameter: str, error: Exception, shared: Shared
) -> object:
    callback = handler.hook.callback
    arguments = {**_arguments(handler.injected, shared), parameter: error}
    result = await settled(typing.cast("object", callback(**arguments)))
    returns = node.definition().returns
    if node.kind == "group" and result is not None:
        problem = f"group '{token(node.name)}' has no result to replace. Return None."
    elif node.kind == "command" and not fits_value(result, returns):
        expected = describe(returns)
        problem = (
            f"command '{token(node.name)}' returns {expected}. "
            f"Make it return {expected}."
        )
    else:
        return result
    message = (
        f"hook function '{callback.__name__}' returned {describe(type(result))}, "
        f"but {problem}"
    )
    raise _mistake(node, message)


async def _run_around(
    node: Node,
    arguments: dict[str, object],
    inside: list[tuple[Node, dict[str, object]]],
    shared: Shared,
) -> object:
    teardown = await _run_group(node, arguments)
    try:
        output = await _run_span(inside, shared)
    except BaseException as error:
        if teardown is not None:
            await _finish(node, teardown, error)
        raise
    if teardown is not None:
        await _finish(node, teardown, None)
    return output


async def _run_hooks(node: Node, event: EventName, shared: Shared) -> None:
    for found in node.definition().hooks:
        if found.hook.event.name != event:
            continue
        callback = found.hook.callback
        result = await settled(
            typing.cast("object", callback(**_arguments(found.injected, shared)))
        )
        if result is not None:
            message = (
                f"hook function '{callback.__name__}' returned "
                f"{type(result).__name__}, but a hook must return None."
            )
            raise _mistake(node, message)


def _arguments(injected: dict[str, type[object]], shared: Shared) -> dict[str, object]:
    arguments: dict[str, object] = {}
    for name, kind in injected.items():
        if kind not in shared:
            shared[kind] = kind()
        arguments[name] = shared[kind]
    return arguments


async def _run_group(node: Node, arguments: dict[str, object]) -> Teardown | None:
    result = node.function(**arguments)
    if not inspect.isgenerator(result) and not inspect.isasyncgen(result):
        result = await settled(result)
        if result is not None:
            raise _returned_a_value(node, result)
        return None
    teardown = typing.cast("Teardown", result)
    finished, yielded = await _step(teardown, None)
    if finished:
        message = (
            f"group '{token(node.name)}' returned before its yield, so nothing "
            "inside it could run. Yield once, between setup and teardown."
        )
        raise _mistake(node, message)
    if yielded is not None:
        await _close(teardown)
        message = (
            f"group '{token(node.name)}' yielded {type(yielded).__name__}, but a "
            "group yields nothing. Use a bare yield, and share data with @state."
        )
        raise _mistake(node, message)
    return teardown


async def _finish(node: Node, teardown: Teardown, error: BaseException | None) -> None:
    finished, result = await _step(teardown, error)
    if not finished:
        await _close(teardown)
        message = (
            f"group '{token(node.name)}' yielded twice. "
            "Yield once, between setup and teardown."
        )
        raise _mistake(node, message)
    if error is None and result is not None:
        raise _returned_a_value(node, result)


async def _step(teardown: Teardown, error: BaseException | None) -> tuple[bool, object]:
    try:
        if isinstance(teardown, AsyncGenerator):
            sent = teardown.asend(None) if error is None else teardown.athrow(error)
            return False, await sent
        return False, teardown.send(None) if error is None else teardown.throw(error)
    except StopIteration as stopped:
        return True, typing.cast("object", stopped.value)
    except StopAsyncIteration:
        return True, None


async def _close(teardown: Teardown) -> None:
    if isinstance(teardown, AsyncGenerator):
        await teardown.aclose()
    else:
        _ = teardown.close()


def _returned_a_value(node: Node, result: object) -> MistakeError:
    message = (
        f"group '{token(node.name)}' returned {type(result).__name__}, "
        "but a group must return None. Print the value, or return it from a command."
    )
    return _mistake(node, message)


def _mistake(node: Node, message: str) -> MistakeError:
    error = TypeError(message)
    error.add_note(location(node))
    return MistakeError(error)


def _answer(request: Request) -> int:
    if request.kind == "completion":
        root = request.nodes[0]
        program = Path(sys.argv[0]).name or token(root.name)
        _ = sys.stdout.write(completion_script(root, request.value, program))
        return 0
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
            error.add_note("Return None, a str, or data that JSON can represent.")
            error.add_note(location(node))
            raise MistakeError(error) from error
    _ = sys.stdout.write(text + "\n")


def _define(root: Root) -> Definition:
    try:
        definition = _definition(root)
        _check_arguments(definition.arguments)
        _check_dependencies(root, definition)
    except Exception as error:
        error.add_note(location(root))
        raise
    return definition


def _definition(root: Root) -> Definition:
    function = root.function
    generator = inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(
        function
    )
    if generator and root.kind == "command":
        message = (
            f"{function.__name__!r} is a generator, but only a group's function "
            "can yield, to run teardown after its commands. "
            "Return the command's result instead."
        )
        raise TypeError(message)
    parameters = inspect.signature(function).parameters
    hints: dict[str, object] = typing.get_type_hints(function, include_extras=True)
    shared = _shared_parameters(root, hints)
    for parameter in parameters.values():
        if parameter.name not in shared:
            _check_parameter(root, parameter, hints.get(parameter.name))
    inputs = [
        _with_handlers(
            root,
            _input(
                parent,
                parameters.get(parent.name),
                hints,
                root.children.get(parent.name, ()),
            ),
        )
        for parent in root.parents
    ]
    hooks = [_hook_call(found) for found in root.hooks]
    return Definition(inputs, root.dependencies, shared, hooks, hints.get("return"))


def _with_handlers(root: Root, target: Input) -> Input:
    attached = root.attached
    handlers = tuple(
        _hook_call(found, on_input=True)
        for found in attached.parents.get(target.name, ())
    )
    child_handlers = tuple(
        tuple(
            _hook_call(found, on_input=True)
            for found in attached.children.get((target.name, index), ())
        )
        for index in range(len(target.children))
    )
    return replace(target, handlers=handlers, child_handlers=child_handlers)


def _hook_call(found: Hook, *, on_input: bool = False) -> HookCall:
    callback = found.callback
    name = callback.__name__
    if inspect.isgeneratorfunction(callback) or inspect.isasyncgenfunction(callback):
        message = (
            f"hook function {name!r} is a generator. Run code before and after "
            "with on.start() and on.exit() hooks, or yield in a group's function."
        )
        raise TypeError(message)
    hints: dict[str, object] = typing.get_type_hints(callback)
    taken: dict[str, type[object]] = {}
    exceptions: list[tuple[str, tuple[type[BaseException], ...]]] = []
    for parameter in inspect.signature(callback).parameters.values():
        annotation = hints.get(parameter.name)
        handles = _exception_types(annotation)
        kind = injected(annotation)
        if parameter.kind not in _UNSUPPORTED_KINDS and handles is not None:
            exceptions.append((parameter.name, handles))
        elif on_input:
            message = (
                f"hook function {name!r} takes parameter '{parameter.name}', but "
                "a handler on a parent or child receives only the exception, "
                "because it runs while the inputs are read. Remove it."
            )
            raise TypeError(message)
        elif parameter.kind not in _UNSUPPORTED_KINDS and kind is not None:
            _take(taken, parameter.name, kind)
        else:
            receives = "an exception, " if found.event.name == "error" else ""
            message = (
                f"hook function {name!r} takes parameter '{parameter.name}', but "
                f"a hook receives only {receives}Context and @state classes. "
                "Annotate it with one, or remove it."
            )
            raise TypeError(message)
    return HookCall(found, taken, _handled(found, exceptions))


def _exception_types(annotation: object) -> tuple[type[BaseException], ...] | None:
    members = union_members(annotation)
    if all(
        isinstance(each, type) and issubclass(each, BaseException) for each in members
    ):
        return typing.cast("tuple[type[BaseException], ...]", members)
    return None


def _handled(
    found: Hook, exceptions: list[tuple[str, tuple[type[BaseException], ...]]]
) -> tuple[str, tuple[type[Exception], ...]] | None:
    name = found.callback.__name__
    if found.event.name != "error":
        if exceptions:
            message = (
                f"hook function {name!r} takes the exception '{exceptions[0][0]}', "
                "but only on.error() hooks receive one."
            )
            raise TypeError(message)
        return None
    if not exceptions:
        message = (
            f"hook function {name!r} handles no exception. Annotate one "
            "parameter with the exceptions it handles, such as exc: ValueError."
        )
        raise TypeError(message)
    if len(exceptions) > 1:
        message = (
            f"hook function {name!r} takes two exceptions, '{exceptions[0][0]}' "
            f"and '{exceptions[1][0]}'. Annotate one parameter, with a union for "
            "several, such as exc: ValueError | KeyError."
        )
        raise TypeError(message)
    parameter, handles = exceptions[0]
    for kind in handles:
        if not issubclass(kind, Exception):
            message = (
                f"hook function {name!r} handles {kind.__name__}, which cliron "
                "always lets through so that Ctrl+C and exits work. Handle "
                "Exception or a subclass of it."
            )
            raise TypeError(message)
    return parameter, typing.cast("tuple[type[Exception], ...]", handles)


def _take(taken: dict[str, type[object]], name: str, kind: type[object]) -> None:
    for other, already in taken.items():
        if already is kind:
            message = (
                f"parameters '{other}' and '{name}' both take {kind.__name__}. "
                "Keep one."
            )
            raise TypeError(message)
    taken[name] = kind


def _shared_parameters(root: Root, hints: dict[str, object]) -> dict[str, type[object]]:
    found: dict[str, type[object]] = {}
    for name, annotation in hints.items():
        kind = injected(annotation)
        if name == "return" or kind is None:
            continue
        for parent in root.parents:
            if parent.name == name:
                message = (
                    f"parameter '{name}' takes {kind.__name__}, so it has no "
                    f"parent. Remove {call(parent)}."
                )
                raise TypeError(message)
        _take(found, name, kind)
    return found


def _check_parameter(
    root: Root, parameter: inspect.Parameter, annotation: object
) -> None:
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
    elif _could_be_state(annotation):
        kind = typing.cast("type[object]", annotation).__name__
        message = (
            f"parameter '{name}' has no parent, and cliron can't convert {kind}. "
            f"Mark {kind} with @state to share one per run, or add a parent above "
            "the function."
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


def _could_be_state(annotation: object) -> bool:
    return (
        isinstance(annotation, type)
        and annotation.__module__ != "builtins"
        and converter_for(annotation) is None
    )


def _in_class(function: FunctionType) -> bool:
    outer = function.__qualname__.rpartition(".")[0]
    return outer != "" and not outer.endswith("<locals>")


def _input(
    parent: Parent,
    parameter: inspect.Parameter | None,
    hints: dict[str, object],
    children: tuple[AnyChild, ...],
) -> Input:
    if parameter is None:
        message = (
            f"{call(parent)} has no parameter. Add {parent.name!r} to the function."
        )
        raise TypeError(message)
    if parent.name not in hints:
        message = (
            f"parameter '{parent.name}' has no type annotation. "
            f"Add one, such as {parent.name}: str."
        )
        raise TypeError(message)
    annotation = hints[parent.name]
    default = typing.cast("object", parameter.default)
    if isinstance(parent, Flag):
        flag_input = _flag(parent, annotation, default)
        return _checked(flag_input, annotation, children, converting=False)
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
    converting = converts(children, annotation)
    converter = converter_for(annotation)
    if converting:
        converter = text_converter(annotation, converter)
    elif converter is None:
        message = (
            f"parameter '{parent.name}' has the type {describe(annotation)}, "
            f"which cliron can't convert. Use {SUPPORTED}, or convert the text "
            "with a child that takes str."
        )
        raise TypeError(message)
    if not isinstance(parent, CommandLineParent | Stdin) and converter.collect:
        message = (
            f"parameter '{parent.name}' has the type {describe(annotation)}, "
            f"but {call(parent)} reads one value. Use a type without list or tuple."
        )
        raise TypeError(message)
    required = default is inspect.Parameter.empty
    target = Input(
        parent, converter, default=None if required else default, required=required
    )
    return _checked(target, annotation, children, converting=converting)


def _checked(
    target: Input,
    annotation: object,
    children: tuple[AnyChild, ...],
    *,
    converting: bool,
) -> Input:
    base = value_type(annotation)
    checked_children = children[1:] if converting else children
    for found in checked_children:
        if base is bool:
            message = (
                f"@{found!r} is below {call(target.parent)}, a bool, "
                "which has nothing to check. Remove it."
            )
            raise TypeError(message)
        problem = misfit(found, base, target.name)
        if problem is not None:
            raise TypeError(problem)
    converter = target.converter
    listed = next((child for child in children if isinstance(child, Choices)), None)
    if converter is not None and listed is not None:
        converter = replace(
            converter, metavar=f"[{'|'.join(listed.labels)}]", choices=listed.labels
        )
    collected = converter is not None and converter.collect is not None
    accepts = base if collected else annotation
    checked = replace(
        target,
        converter=converter,
        children=children,
        accepts=accepts,
        annotation=annotation,
    )
    _check_default(checked, checked_children)
    return checked


def _check_default(target: Input, children: tuple[AnyChild, ...]) -> None:
    if target.required or target.default is None:
        return
    where = "an item of the default" if target.multiple else "the default"
    checks = [found for found in children if not checks_on_run(found)]
    for item in target.default_items:
        value = item
        for found in checks:
            try:
                value = run_child(found, value)
            except ValueError as error:
                message = (
                    f"@{found!r} rejects {where} of parameter '{target.name}': "
                    f"{error} Change one of them."
                )
                raise ValueError(message) from None


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
        f"but a flag is a bool or an int. Use {name}: bool = False, "
        f"or {name}: int = 0 to count."
    )
    raise TypeError(message)


def _check_dependencies(root: Root, definition: Definition) -> None:
    required = {target.name for target in definition.inputs if target.required}
    for found in definition.dependencies:
        for name in found.names:
            if name in required:
                hints: dict[str, object] = typing.get_type_hints(
                    root.function, include_extras=True
                )
                example = _optional(name, hints[name])
                message = (
                    f"{found.call} names {name!r}, which has no default, so it is "
                    f"always given. Give it one, such as {example}, "
                    "or remove the dependency."
                )
                raise ValueError(message)
    problem = cycle_problem(definition.dependencies, definition.labels)
    if problem is not None:
        raise ValueError(problem)


def _optional(name: str, annotation: object) -> str:
    arguments: tuple[object, ...] = typing.get_args(annotation)
    optional = "" if NoneType in arguments else " | None"
    return f"{name}: {describe(annotation)}{optional} = None"


def _clash_fix(key: str) -> str:
    if key.startswith("--"):
        return "Rename one of them."
    if key.startswith("-"):
        return "Give one of them another short flag."
    if key.startswith("$"):
        return "Give one of them another variable."
    if key == "stdin":
        return "Remove one."
    return "Rename one of them."


def _check_arguments(arguments: tuple[Input, ...]) -> None:
    optional: Input | None = None
    for index, target in enumerate(arguments):
        if target.multiple and index < len(arguments) - 1:
            message = (
                f"argument '{target.name}' takes several values, "
                "so it must be the last argument. "
                "Move its @argument below the others."
            )
            raise TypeError(message)
        if target.required and optional is not None:
            message = (
                f"argument '{target.name}' has no default, so it can't come after "
                f"argument '{optional.name}', which has one. "
                f"Give '{target.name}' a default, or move its @argument above "
                f"'{optional.name}'."
            )
            raise TypeError(message)
        if not target.required:
            optional = target
