import functools
import re
from collections.abc import AsyncIterator, Callable, Iterator
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Annotated, Literal, cast

import pytest

from cliron import argument, command, env, flag, group, option, stdin
from cliron.testing import run, validate

if TYPE_CHECKING:
    from decimal import Decimal


class Clash(Enum):
    RED = 1
    red = 2


class Empty(Enum): ...


class Greeter:
    def __call__(self, name: str) -> str:
        return name


Decorated = Callable[[Callable[..., object]], Callable[..., object]]
Check = Callable[..., object]

SUPPORTED = (
    "str, int, float, Path, date, datetime, time, an Enum, a Literal of strings, "
    "X | None, list[X] and tuple[X, ...]"
)

NAME_RULE = (
    "A name starts with a lowercase letter "
    "and contains only lowercase letters, digits and single underscores."
)

BAD_NAMES = pytest.mark.parametrize(
    ("name", "message"),
    [
        ("dryRun", "'dryRun' isn't snake_case. Use 'dry_run'."),
        ("DryRun", "'DryRun' isn't snake_case. Use 'dry_run'."),
        ("dry-run", "'dry-run' isn't snake_case. Use 'dry_run'."),
        ("HTTPServer", "'HTTPServer' isn't snake_case. Use 'http_server'."),
        ("2fast", f"'2fast' isn't snake_case. {NAME_RULE}"),
        ("", f"'' isn't snake_case. {NAME_RULE}"),
        ("café", f"'café' isn't snake_case. {NAME_RULE}"),
        ("naïve", f"'naïve' isn't snake_case. {NAME_RULE}"),
    ],
)

ENTRY_POINTS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def defined_at(kind: str, name: str, line: int) -> str:
    return f"in {kind} '{name}', defined at {__file__}:{line}"


@BAD_NAMES
@pytest.mark.parametrize(
    "decorator", [argument, option, flag, env, stdin, command, group]
)
def test_decorator_rejects_name_that_isnt_snake_case(
    decorator: Callable[[str], Decorated], name: str, message: str
) -> None:
    def greet(value: str) -> str:
        return value

    with pytest.raises(ValueError, match=exactly(message)):
        _ = decorator(name)(greet)


@pytest.mark.parametrize("decorator", [option, flag])
@pytest.mark.parametrize("short", ["c", "--c", "-cc", "-1", "-é"])
def test_short_flag_must_be_a_dash_and_one_letter(
    decorator: Callable[[str, str], Decorated], short: str
) -> None:
    def greet(*, color: bool = False) -> bool:
        return color

    message = f"{short!r} isn't a short flag. Use a dash and one letter, such as '-c'."
    with pytest.raises(ValueError, match=exactly(message)):
        _ = decorator("color", short)(greet)


@pytest.mark.parametrize(
    ("parent", "name"),
    [
        (argument, "argument"),
        (option, "option"),
        (flag, "flag"),
        (env, "env"),
        (stdin, "stdin"),
    ],
)
@pytest.mark.parametrize("root", [command, group])
def test_parent_decorator_above_root_decorator_is_rejected(
    parent: Callable[[str], Decorated], name: str, root: Callable[[str], Decorated]
) -> None:
    @root("greet")
    def greet(count: int = 0) -> int:
        return count

    message = f"@{name} must decorate a function, so it goes below @command or @group."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = parent("count")(greet)


@pytest.mark.parametrize(("root", "name"), [(command, "command"), (group, "group")])
def test_root_decorator_rejects_something_that_isnt_a_function(
    root: Callable[[str], Decorated], name: str
) -> None:
    @command("hello")
    def hello() -> None: ...

    with pytest.raises(TypeError, match=exactly(f"@{name} must decorate a function.")):
        _ = root("greet")(hello)


def test_group_rejects_an_argument() -> None:
    @argument("name")
    def cli(name: str) -> None:
        _ = name

    message = "group 'cli' can't take arguments. Use @option(\"name\") instead."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = group("cli")(cli)


def test_two_parents_with_the_same_name_are_rejected() -> None:
    @option("count")
    @flag("count")
    def greet(count: int = 0) -> int:
        return count

    message = (
        'parameter \'count\' has two parents, @option("count") and @flag("count").'
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("greet")(greet)


def test_an_option_and_an_env_with_the_same_name_are_rejected() -> None:
    @option("tag")
    @env("tag")
    def add(tag: str = "") -> str:
        return tag

    message = 'parameter \'tag\' has two parents, @option("tag") and @env("tag").'
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("add")(add)


def test_two_parents_with_the_same_short_flag_are_rejected() -> None:
    @option("count", "-c")
    @flag("color", "-c")
    def greet(count: int = 1, *, color: bool = False) -> str:
        return f"{count} {color}"

    message = '-c is used by both @option("count") and @flag("color").'
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("greet")(greet)


@pytest.mark.parametrize("first", ["command", "group"])
@pytest.mark.parametrize("second", ["command", "group"])
def test_group_rejects_two_commands_with_the_same_name(first: str, second: str) -> None:
    @group("cli")
    def cli() -> None: ...

    def items() -> None: ...

    cli.add(command("list")(items) if first == "command" else group("list")(items))
    message = "group 'cli' already has a command 'list'."
    with pytest.raises(ValueError, match=exactly(message)):
        cli.add(command("list")(items) if second == "command" else group("list")(items))


@ENTRY_POINTS
def test_parameter_without_parent_is_rejected(check: Check) -> None:
    @command("greet")
    @argument("name")
    def greet(name: str, count: int = 1) -> str:
        return name * count

    message = (
        "parameter 'count' has no parent. "
        'Add one above the function, for example @option("count").'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
@pytest.mark.parametrize(
    ("parent", "name"),
    [
        (argument, "argument"),
        (option, "option"),
        (flag, "flag"),
        (env, "env"),
        (stdin, "stdin"),
    ],
)
def test_parent_without_parameter_is_rejected(
    check: Check, parent: Callable[[str], Decorated], name: str
) -> None:
    def greet() -> None: ...

    cli = command("greet")(parent("count")(greet))
    message = f"@{name}(\"count\") has no parameter. Add 'count' to the function."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
def test_parameter_without_annotation_is_rejected(check: Check) -> None:
    @argument("name")
    def greet(name: str) -> str:
        return name

    del greet.__annotations__["name"]
    cli = command("greet")(greet)
    message = "parameter 'name' needs a type annotation."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
@pytest.mark.parametrize(
    ("annotation", "description"),
    [
        (int | str, "int | str"),
        (Annotated[int, "meta"], "typing.Annotated[int, 'meta']"),
        (Literal[1, 2], "typing.Literal[1, 2]"),
        (dict[str, int], "dict[str, int]"),
        (tuple[int, str], "tuple[int, str]"),
        (list[list[int]], "list[list[int]]"),
        (object, "object"),
    ],
)
def test_unsupported_type_is_rejected(
    check: Check, annotation: object, description: str
) -> None:
    @option("value")
    def greet(value: object) -> object:
        return value

    greet.__annotations__["value"] = annotation
    cli = command("greet")(greet)
    message = (
        f"parameter 'value' has the type {description}, "
        f"which cliron can't convert. Use {SUPPORTED}."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
@pytest.mark.parametrize("parent", [argument, option])
def test_bool_parameter_needs_a_flag(
    check: Check, parent: Callable[[str], Decorated]
) -> None:
    def greet(*, shout: bool = False) -> bool:
        return shout

    cli = command("greet")(parent("shout")(greet))
    message = "parameter 'shout' is a bool. Use @flag(\"shout\")."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
@pytest.mark.parametrize(
    ("annotation", "description"),
    [(str, "str"), (float, "float"), (bool | None, "bool | None")],
)
def test_flag_must_be_a_bool_or_an_int(
    check: Check, annotation: object, description: str
) -> None:
    @flag("level")
    def greet(*, level: object = None) -> object:
        return level

    greet.__annotations__["level"] = annotation
    cli = command("greet")(greet)
    message = (
        f"flag 'level' has the type {description}, but a flag is a bool or an int."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
def test_bool_flag_defaulting_to_true_suggests_a_negated_flag(check: Check) -> None:
    @command("greet")
    @flag("color")
    def greet(*, color: bool = True) -> bool:
        return color

    message = (
        "flag 'color' is off until passed, so it must default to False: "
        "color: bool = False. "
        'To turn something off, use @flag("no_color") with no_color: bool = False.'
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_bool_flag_defaulting_to_none_is_rejected(check: Check) -> None:
    @flag("color")
    def greet(*, color: bool = False) -> bool:
        return color

    greet.__kwdefaults__ = {"color": None}
    cli = command("greet")(greet)
    message = (
        "flag 'color' is off until passed, so it must default to False: "
        "color: bool = False."
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
def test_bool_flag_without_default_is_rejected(check: Check) -> None:
    @command("greet")
    @flag("color")
    def greet(*, color: bool) -> bool:
        return color

    message = (
        "flag 'color' is off until passed, so it must default to False: "
        "color: bool = False."
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
@pytest.mark.parametrize("default", [1, False])
def test_counting_flag_must_default_to_zero(check: Check, default: int) -> None:
    @flag("verbose")
    def greet(*, verbose: int = 0) -> int:
        return verbose

    greet.__kwdefaults__ = {"verbose": default}
    cli = command("greet")(greet)
    message = "flag 'verbose' counts from 0, so it must default to 0: verbose: int = 0."
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(cli)
    line = greet.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "greet", line)]


@ENTRY_POINTS
def test_required_argument_after_optional_argument_is_rejected(check: Check) -> None:
    @command("copy")
    @argument("source")
    @argument("target")
    def copy(target: str, source: str = ".") -> str:
        return f"{source} {target}"

    message = (
        "argument 'target' has no default, "
        "so it can't come after argument 'source', which has one."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(copy)


@ENTRY_POINTS
def test_list_argument_must_come_last(check: Check) -> None:
    @command("copy")
    @argument("sources")
    @argument("target")
    def copy(sources: list[str], target: str) -> str:
        return f"{sources} {target}"

    message = (
        "argument 'sources' takes several values, so it must be the last argument."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(copy)


@ENTRY_POINTS
def test_var_positional_parameter_is_rejected(check: Check) -> None:
    @command("greet")
    @argument("names")
    def greet(*names: str) -> str:
        return " ".join(names)

    message = (
        "parameter '*names' can't be filled from the command line. For several "
        'values, use names: list[str] with @argument("names").'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_var_keyword_parameter_is_rejected(check: Check) -> None:
    @command("greet")
    @option("extra")
    def greet(**extra: str) -> str:
        return " ".join(extra)

    message = (
        "parameter '**extra' can't be filled from the command line. "
        "Give each input its own parameter."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_positional_only_parameter_is_rejected(check: Check) -> None:
    @command("greet")
    @argument("name")
    def greet(name: str, /) -> str:
        return name

    message = (
        "parameter 'name' is positional-only, but cliron passes every value "
        "by name. Remove the '/'."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_async_function_is_rejected(check: Check) -> None:
    @command("greet")
    async def greet() -> None: ...

    message = "'greet' is async, and cliron doesn't run async functions yet."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_async_generator_function_is_rejected(check: Check) -> None:
    @command("greet")
    async def greet() -> AsyncIterator[str]:
        yield "Hello!"

    message = "'greet' is async, and cliron doesn't run async functions yet."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_generator_function_is_rejected(check: Check) -> None:
    @command("greet")
    def greet() -> Iterator[str]:
        yield "Hello!"

    message = "'greet' is a generator, and cliron doesn't run generator functions yet."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(greet)


@ENTRY_POINTS
def test_build_error_notes_the_command_and_where_it_is_defined(check: Check) -> None:
    def greet(name: str) -> str:
        return name

    cli = command("greet")(greet)
    with pytest.raises(TypeError, match="parameter 'name' has no parent") as info:
        _ = check(cli)
    line = greet.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "greet", line)]


@ENTRY_POINTS
def test_build_error_notes_the_group_and_where_it_is_defined(check: Check) -> None:
    def tool(level: int) -> None:
        _ = level

    cli = group("tool")(tool)
    with pytest.raises(TypeError, match="parameter 'level' has no parent") as info:
        _ = check(cli)
    line = tool.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("group", "tool", line)]


@ENTRY_POINTS
def test_unresolvable_annotation_gets_the_note(check: Check) -> None:
    @option("amount")
    def total(amount: "Decimal") -> str:
        return str(amount)

    cli = command("total")(total)
    with pytest.raises(NameError, match="Decimal") as info:
        _ = check(cli)
    line = total.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "total", line)]


def test_validate_checks_nested_commands_that_no_run_reaches() -> None:
    @group("cli")
    def cli() -> None: ...

    @command("ping")
    def ping() -> str:
        return "pong"

    cli.add(ping)

    @group("tasks")
    def tasks() -> None: ...

    cli.add(tasks)

    def add(title: str) -> str:
        return title

    tasks.add(command("add")(add))
    result = run(cli, ["ping"])
    assert (result.returncode, result.stdout, result.stderr) == (0, "pong\n", "")
    message = (
        "parameter 'title' has no parent. "
        'Add one above the function, for example @option("title").'
    )
    with pytest.raises(TypeError, match=exactly(message)) as info:
        validate(cli)
    line = add.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "add", line)]


def test_validate_accepts_a_valid_cli_twice() -> None:
    @group("cli")
    @flag("verbose", "-v")
    def cli(*, verbose: bool = False) -> None:
        _ = verbose

    @command("greet")
    @argument("name")
    @option("count", "-c")
    def greet(name: str, count: int = 1) -> str:
        return " ".join([f"Hello, {name}!"] * count)

    cli.add(greet)

    validate(cli)
    validate(cli)
    result = run(cli, ["-v", "greet", "Ada", "-c", "2"])
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "Hello, Ada! Hello, Ada!\n",
        "",
    )


@pytest.mark.parametrize(
    ("decorator", "name"),
    [
        (argument, "argument"),
        (option, "option"),
        (flag, "flag"),
        (env, "env"),
        (stdin, "stdin"),
        (command, "command"),
        (group, "group"),
    ],
)
def test_decorator_without_parentheses_is_rejected(
    decorator: Callable[..., object], name: str
) -> None:
    def greet() -> None: ...

    message = f'@{name} needs a name in parentheses, such as @{name}("name").'
    with pytest.raises(TypeError, match=exactly(message)):
        _ = decorator(greet)


@pytest.mark.parametrize(
    ("node", "kind"), [(len, "builtin_function_or_method"), ("x", "str")]
)
def test_add_rejects_something_that_isnt_a_command_or_group(
    node: object, kind: str
) -> None:
    @group("cli")
    def cli() -> None: ...

    add = cast("Callable[..., object]", cli.add)
    message = (
        f"group 'cli' can only add commands and groups, not a {kind}. "
        'Decorate it with @command("name") or @group("name") first.'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = add(node)
    assert cli.commands == {}


def test_add_rejects_a_plain_function() -> None:
    @group("cli")
    def cli() -> None: ...

    def items() -> None: ...

    add = cast("Callable[..., object]", cli.add)
    message = (
        "group 'cli' can only add commands and groups, not a function. "
        'Decorate it with @command("name") or @group("name") first.'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = add(items)


def test_group_cant_be_added_to_itself() -> None:
    @group("cli")
    def cli() -> None: ...

    with pytest.raises(
        ValueError, match=exactly("group 'cli' can't be added to itself.")
    ):
        cli.add(cli)


def test_group_cant_be_added_to_a_group_inside_it() -> None:
    @group("outer")
    def outer() -> None: ...

    @group("middle")
    def middle() -> None: ...

    @group("inner")
    def inner() -> None: ...

    outer.add(middle)
    middle.add(inner)
    message = "group 'outer' contains 'inner', so it can't be added to it."
    with pytest.raises(ValueError, match=exactly(message)):
        inner.add(outer)


@pytest.mark.parametrize("decorator", [argument, option, flag, env, stdin])
def test_parent_name_cant_be_a_python_keyword(
    decorator: Callable[[str], Decorated],
) -> None:
    message = (
        "'from' is a Python keyword, so no parameter can have that name. "
        "Use 'from_': users don't type the trailing underscore."
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = decorator("from")


def test_parent_name_that_becomes_a_keyword_gets_a_trailing_underscore() -> None:
    with pytest.raises(
        ValueError, match=exactly("'From' isn't snake_case. Use 'from_'.")
    ):
        _ = option("From")


@pytest.mark.parametrize("name", ["count__", "_", "_count"])
def test_parent_name_may_end_with_only_one_underscore(name: str) -> None:
    with pytest.raises(ValueError, match="isn't snake_case"):
        _ = option(name)


def test_command_name_cant_end_with_an_underscore() -> None:
    with pytest.raises(
        ValueError, match=exactly("'from_' isn't snake_case. Use 'from'.")
    ):
        _ = command("from_")


def test_two_parents_typed_the_same_are_rejected() -> None:
    @option("count")
    @option("count_")
    def greet(count: int = 1, count_: int = 1) -> str:
        return f"{count} {count_}"

    message = '--count is used by both @option("count") and @option("count_").'
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("greet")(greet)


def test_command_name_can_be_a_python_keyword() -> None:
    @group("cli")
    def cli() -> None: ...

    @command("import")
    def load() -> str:
        return "loaded"

    cli.add(load)

    result = run(cli, ["import"])
    assert (result.returncode, result.stdout, result.stderr) == (0, "loaded\n", "")


@ENTRY_POINTS
def test_method_says_cliron_calls_plain_functions(check: Check) -> None:
    class App:
        def serve(self, port: int = 8000) -> str:
            return f"{self} {port}"

    cli = command("serve")(option("port")(App.serve))
    message = (
        "parameter 'self' has no parent. cliron calls plain functions, "
        "not methods, so define the function outside a class."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(cli)


@ENTRY_POINTS
def test_plain_function_parameter_named_cls_gets_the_usual_advice(
    check: Check,
) -> None:
    @command("train")
    @option("epochs")
    def train(cls: str, epochs: int = 1) -> str:
        return cls * epochs

    message = (
        "parameter 'cls' has no parent. "
        'Add one above the function, for example @option("cls").'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(train)


@ENTRY_POINTS
def test_parameter_whose_name_isnt_snake_case_must_be_renamed(check: Check) -> None:
    @command("build")
    def build(dry__run: int = 0) -> str:
        return str(dry__run)

    message = (
        "parameter 'dry__run' has no parent, and a parent's name must be "
        "snake_case. Rename the parameter to dry_run."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(build)


@ENTRY_POINTS
def test_parameter_without_a_snake_case_suggestion_must_be_renamed(
    check: Check,
) -> None:
    @command("build")
    def build(_: int = 0) -> str:
        return str(_)

    message = (
        "parameter '_' has no parent, and a parent's name must be "
        "snake_case. Rename the parameter to a snake_case name."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(build)


@ENTRY_POINTS
def test_enum_members_typed_the_same_are_rejected(check: Check) -> None:
    @command("paint")
    @option("color")
    def paint(color: Clash = Clash.RED) -> str:
        return color.name

    message = "Clash.RED and Clash.red would both be typed 'red'. Rename one of them."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(paint)


@ENTRY_POINTS
def test_enum_without_members_is_rejected(check: Check) -> None:
    @command("pick")
    @option("choice")
    def pick(choice: Empty | None = None) -> str:
        return repr(choice)

    with pytest.raises(
        TypeError, match=exactly("Empty has no members to choose from.")
    ):
        _ = check(pick)


def test_build_error_note_names_the_wrapped_function() -> None:
    def greet(name: str) -> str:
        return name

    @functools.wraps(greet)
    def logged(name: str) -> str:
        return greet(name)

    cli = command("greet")(logged)
    with pytest.raises(TypeError, match="parameter 'name' has no parent") as info:
        validate(cli)
    line = greet.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "greet", line)]


def test_build_error_note_falls_back_when_the_wrapped_object_isnt_a_function() -> None:
    def logged(name: str) -> str:
        return name

    vars(logged)["__wrapped__"] = Greeter()
    cli = command("greet")(logged)
    with pytest.raises(TypeError, match="parameter 'name' has no parent") as info:
        validate(cli)
    line = logged.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "greet", line)]


@pytest.mark.parametrize("decorator", [option, flag])
@pytest.mark.parametrize("short", [1, True])
def test_short_flag_that_isnt_a_string_is_rejected(
    decorator: Callable[..., object], short: object
) -> None:
    message = (
        f"the short flag must be a string such as '-c', not {short!r}. "
        "A default value goes in the function's signature."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = decorator("count", short)


@pytest.mark.parametrize(
    ("name", "suggestion"), [("import_", "import"), ("Import", "import")]
)
def test_command_name_may_be_suggested_as_a_python_keyword(
    name: str, suggestion: str
) -> None:
    message = f"{name!r} isn't snake_case. Use {suggestion!r}."
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command(name)


@ENTRY_POINTS
def test_var_positional_parameter_of_a_group_suggests_an_option(check: Check) -> None:
    @group("files")
    def files(*paths: str) -> None:
        _ = paths

    message = (
        "parameter '*paths' can't be filled from the command line. For several "
        'values, use paths: list[str] with @option("paths").'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(files)


@ENTRY_POINTS
def test_parameter_named_after_a_keyword_gets_the_usual_advice(check: Check) -> None:
    @command("copy")
    def copy(from_: str) -> str:
        return from_

    message = (
        "parameter 'from_' has no parent. "
        'Add one above the function, for example @option("from_").'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(copy)


@ENTRY_POINTS
def test_parameter_whose_suggestion_is_a_keyword_is_renamed_with_an_underscore(
    check: Check,
) -> None:
    @command("check")
    def check_(if__: str = "") -> str:
        return if__

    message = (
        "parameter 'if__' has no parent, and a parent's name must be "
        "snake_case. Rename the parameter to if_."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(check_)
