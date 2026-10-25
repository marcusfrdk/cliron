import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import pytest

from cliron import Context, command, group, option, state
from cliron.testing import run, validate

CREATED: list[str] = []


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@state
class Notes:
    database: str = ""
    quiet: bool = False


@state
class Settings:
    color: str = "auto"


@state
class Counted:
    def __init__(self) -> None:
        CREATED.append("Counted")


@state
@dataclass
class Plan:
    steps: int = 1


@state
class Lookup(dict[str, str]):
    pass


@dataclass
class NeedsDatabase:
    database: str


class Bag:
    tags: ClassVar[list[str]] = []


class Counts:
    seen: ClassVar[dict[str, int]] = {}


class Inherited(Bag):
    pass


class Database:
    pass


def test_a_parameter_annotated_context_receives_the_path() -> None:
    @command("greet")
    @option("name")
    def greet(run_info: Context, name: str = "Ada") -> str:
        return f"{run_info.path} {name}"

    assert run(greet, ["--name", "Grace"]).stdout == "('greet',) Grace\n"


def test_every_function_in_a_run_gets_the_same_context() -> None:
    seen: list[Context] = []

    @group("notes")
    def notes(ctx: Context) -> None:
        seen.append(ctx)

    @group("tags")
    def tags() -> None: ...

    @command("rename_tag")
    def rename_tag(ctx: Context) -> str:
        seen.append(ctx)
        return " ".join(ctx.path)

    tags.add(rename_tag)
    notes.add(tags)

    assert run(notes, ["tags", "rename-tag"]).stdout == "notes tags rename-tag\n"
    assert seen[0] is seen[1]


def test_a_group_and_its_command_share_the_runs_state() -> None:
    @group("notes")
    @option("database")
    def notes(shared: Notes, database: str = "notes.db") -> None:
        shared.database = database

    @command("add")
    def add(shared: Notes) -> str:
        return f"{shared.database} {shared.quiet}"

    notes.add(add)

    assert run(notes, ["--database", "work.db", "add"]).stdout == "work.db False\n"
    assert run(notes, ["add"]).stdout == "notes.db False\n"


def test_each_state_class_has_one_instance_per_run() -> None:
    seen: list[object] = []

    @group("tool")
    def tool(settings: Settings, plan: Plan, lookup: Lookup) -> None:
        seen.extend([settings, plan, lookup])

    @command("show")
    def show(settings: Settings, plan: Plan, lookup: Lookup, ctx: Context) -> str:
        seen.extend([settings, plan, lookup])
        return f"{settings.color} {plan.steps} {dict(lookup)} {ctx.path}"

    tool.add(show)

    assert run(tool, ["show"]).stdout == "auto 1 {} ('tool', 'show')\n"
    first_function, second_function = seen[:3], seen[3:]
    assert all(map(operator.is_, first_function, second_function))


def test_a_state_class_is_created_only_when_a_function_asks_for_it() -> None:
    @command("quiet")
    def quiet() -> str:
        return "quiet"

    @group("loud")
    def loud(first: Counted) -> None:
        _ = first

    @command("again")
    def again(second: Counted) -> str:
        return type(second).__name__

    loud.add(again)
    CREATED.clear()

    assert run(quiet, []).stdout == "quiet\n"
    assert CREATED == []
    assert run(loud, ["again"]).stdout == "Counted\n"
    assert CREATED == ["Counted"]


def test_a_function_takes_each_kind_once() -> None:
    @command("greet")
    def greet(first: Notes, second: Notes) -> str:
        return f"{first} {second}"

    message = "parameters 'first' and 'second' both take Notes. Keep one."
    with pytest.raises(TypeError, match=exactly(message)):
        validate(greet)


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        (
            Database,
            (
                "parameter 'session' has no parent, and cliron can't convert "
                "Database. Mark Database with @state to share one per run, or add "
                "a parent above the function."
            ),
        ),
        (
            dict,
            (
                "parameter 'session' has no parent. Add one above the function, "
                'for example @option("session").'
            ),
        ),
    ],
    ids=["class", "built-in"],
)
def test_an_unmarked_class_without_a_parent_suggests_state(
    annotation: object, message: str
) -> None:
    def add(session: object) -> str:
        return f"{session}"

    add.__annotations__["session"] = annotation

    with pytest.raises(TypeError, match=exactly(message)):
        validate(command("add")(add))


def test_a_shared_parameter_has_no_parent() -> None:
    @command("greet")
    @option("ctx")
    def greet(ctx: Context) -> str:
        return f"{ctx}"

    message = (
        "parameter 'ctx' takes Context, so it has no parent. Remove @option(\"ctx\")."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        validate(greet)


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        (42, "@state must decorate a class, such as class Notes:, not 42."),
        (
            NeedsDatabase,
            (
                "@state class NeedsDatabase must work without arguments, but "
                "missing a required argument: 'database'. Give each of its "
                "fields a default, or none."
            ),
        ),
        (
            Bag,
            (
                "Bag.tags defaults to a list, which every run would share. "
                "Leave it without a default and set it in a function."
            ),
        ),
        (
            Counts,
            (
                "Counts.seen defaults to a dict, which every run would share. "
                "Leave it without a default and set it in a function."
            ),
        ),
        (
            Inherited,
            (
                "Inherited.tags defaults to a list, which every run would share. "
                "Leave it without a default and set it in a function."
            ),
        ),
    ],
    ids=["not-a-class", "arguments", "list", "dict", "inherited"],
)
@pytest.mark.parametrize("mark", [state])
def test_state_rejects_what_cant_be_shared_safely(
    mark: Callable[..., object], cls: object, message: str
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = mark(cls)
