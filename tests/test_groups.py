import re

import pytest

from cliron import argument, command, flag, group, option
from cliron.testing import run, validate


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ["-v", "tags", "--color", "blue", "add", "urgent"],
            [("notes", True), ("tags", "blue"), ("add", "urgent")],
        ),
        (
            ["tags", "add", "urgent"],
            [("notes", False), ("tags", "red"), ("add", "urgent")],
        ),
    ],
)
def test_callbacks_run_top_down_with_their_own_values(
    args: list[str], expected: list[tuple[str, object]]
) -> None:
    calls: list[tuple[str, object]] = []

    @group("notes")
    @flag("verbose", "-v")
    def notes(*, verbose: bool = False) -> None:
        calls.append(("notes", verbose))

    @group("tags")
    @option("color")
    def tags(color: str = "red") -> None:
        calls.append(("tags", color))

    notes.add(tags)

    @command("add")
    @argument("name")
    def add(name: str) -> None:
        calls.append(("add", name))

    tags.add(add)

    result = run(notes, args)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert calls == expected


def test_nested_group_runs_the_command_it_names() -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @command("list")
    def list_notes() -> None:
        calls.append("list notes")

    notes.add(list_notes)

    @group("tags")
    def tags() -> None:
        calls.append("tags")

    notes.add(tags)

    @command("list")
    def list_tags() -> None:
        calls.append("list tags")

    tags.add(list_tags)

    result = run(notes, ["tags", "list"])

    assert result.returncode == 0
    assert calls == ["notes", "tags", "list tags"]


def test_names_are_typed_in_kebab_case() -> None:
    calls: list[str] = []

    @group("tasks")
    def tasks() -> None:
        calls.append("tasks")

    @group("due_soon")
    def due_soon() -> None:
        calls.append("due_soon")

    tasks.add(due_soon)

    @command("create_task")
    def create_task() -> None:
        calls.append("create_task")

    due_soon.add(create_task)

    result = run(tasks, ["due-soon", "create-task"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert calls == ["tasks", "due_soon", "create_task"]


def test_command_name_typed_in_snake_case_is_unknown() -> None:
    calls: list[str] = []

    @group("tasks")
    def tasks() -> None:
        calls.append("tasks")

    @command("create_task")
    def create_task() -> None:
        calls.append("create_task")

    tasks.add(create_task)

    result = run(tasks, ["create_task"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: 'create_task' isn't a tasks command. Did you mean 'create-task'?\n"
    )
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [
        ["-qf", "work", "add", "milk"],
        ["--folder", "work", "-q", "add", "milk"],
        ["-q", "--folder=work", "add", "milk"],
    ],
)
def test_group_options_go_right_after_the_group(args: list[str]) -> None:
    calls: list[tuple[str, ...]] = []

    @group("notes")
    @flag("quiet", "-q")
    @option("folder", "-f")
    def notes(folder: str = "inbox", *, quiet: bool = False) -> None:
        calls.append(("notes", folder, str(quiet)))

    @command("add")
    @argument("text")
    def add(text: str) -> None:
        calls.append(("add", text))

    notes.add(add)

    result = run(notes, args)

    assert result.returncode == 0
    assert result.stderr == ""
    assert calls == [("notes", "work", "True"), ("add", "milk")]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-q", "add"], [("notes", True), ("add", False)]),
        (["add", "-q"], [("notes", False), ("add", True)]),
        (["-q", "add", "-q"], [("notes", True), ("add", True)]),
    ],
)
def test_group_and_command_each_read_their_own_short_flag(
    args: list[str], expected: list[tuple[str, bool]]
) -> None:
    calls: list[tuple[str, bool]] = []

    @group("notes")
    @flag("quiet", "-q")
    def notes(*, quiet: bool = False) -> None:
        calls.append(("notes", quiet))

    @command("add")
    @flag("quick", "-q")
    def add(*, quick: bool = False) -> None:
        calls.append(("add", quick))

    notes.add(add)

    result = run(notes, args)

    assert result.returncode == 0
    assert result.stderr == ""
    assert calls == expected


@pytest.mark.parametrize(
    ("args", "written"),
    [
        (["add", "-q", "milk"], "-q"),
        (["add", "--quiet", "milk"], "--quiet"),
        (["add", "-f", "work", "milk"], "-f"),
        (["add", "--folder", "work", "milk"], "--folder"),
        (["add", "--folder=work", "milk"], "--folder"),
        (["add", "milk", "-f", "work"], "-f"),
    ],
)
def test_group_option_after_the_command_belongs_to_the_group(
    args: list[str], written: str
) -> None:
    calls: list[str] = []

    @group("notes")
    @flag("quiet", "-q")
    @option("folder", "-f")
    def notes(folder: str = "inbox", *, quiet: bool = False) -> None:
        calls.append(f"notes {folder} {quiet}")

    @command("add")
    @argument("text")
    def add(text: str) -> None:
        calls.append(f"add {text}")

    notes.add(add)

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: {written} belongs to 'notes'. Write it right after 'notes'.\n"
    )
    assert calls == []


def test_misplaced_option_takes_a_value_when_its_owner_does() -> None:
    calls: list[str] = []

    @group("notes")
    @option("tag")
    def notes(tag: str = "") -> None:
        calls.append(tag)

    @command("add")
    @flag("tags")
    @argument("text")
    def add(text: str, *, tags: bool = False) -> None:
        calls.append(f"{text} {tags}")

    notes.add(add)

    result = run(notes, ["add", "--tag", "work", "milk"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: --tag belongs to 'notes'. Write it right after 'notes'.\n"
    )
    assert calls == []


def test_misplaced_option_takes_no_value_when_its_owner_is_a_flag() -> None:
    calls: list[str] = []

    @group("notes")
    @flag("verbose")
    def notes(*, verbose: bool = False) -> None:
        calls.append(str(verbose))

    @command("add")
    @option("verbosity")
    @argument("text")
    def add(text: str, verbosity: int = 0) -> None:
        calls.append(f"{text} {verbosity}")

    notes.add(add)

    result = run(notes, ["add", "--verbose", "milk"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: --verbose belongs to 'notes'. Write it right after 'notes'.\n"
    )
    assert calls == []


def test_misplaced_option_does_not_stop_the_check() -> None:
    calls: list[str] = []

    @group("notes")
    @option("folder", "-f")
    def notes(folder: str = "inbox") -> None:
        calls.append(folder)

    @command("add")
    @argument("text")
    def add(text: str) -> None:
        calls.append(text)

    notes.add(add)

    result = run(notes, ["add", "-f", "work", "milk", "extra"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: -f belongs to 'notes'. Write it right after 'notes'.\n"
        "error: unexpected argument 'extra'.\n"
    )
    assert calls == []


def test_group_option_after_a_sub_subcommand_belongs_to_the_group() -> None:
    calls: list[str] = []

    @group("notes")
    @option("folder", "-f")
    def notes(folder: str = "inbox") -> None:
        calls.append(folder)

    @group("tags")
    def tags() -> None:
        calls.append("tags")

    notes.add(tags)

    @command("add")
    @argument("name")
    def add(name: str) -> None:
        calls.append(name)

    tags.add(add)

    result = run(notes, ["tags", "add", "-f", "work", "urgent"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: -f belongs to 'notes'. Write it right after 'notes'.\n"
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "written"),
    [
        (["-q", "add"], "-q"),
        (["--quick", "add"], "--quick"),
        (["--title", "draft", "add"], "--title"),
    ],
)
def test_command_option_before_the_command_belongs_to_the_command(
    args: list[str], written: str
) -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @command("add")
    @flag("quick", "-q")
    @option("title")
    def add(title: str = "untitled", *, quick: bool = False) -> None:
        calls.append(f"{title} {quick}")

    notes.add(add)

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: {written} belongs to 'add'. Write it right after 'add'.\n"
    )
    assert calls == []


def test_option_owned_by_two_nodes_on_the_path_names_both() -> None:
    calls: list[str] = []

    @group("notes")
    @flag("quiet", "-q")
    def notes(*, quiet: bool = False) -> None:
        calls.append(f"notes {quiet}")

    @group("tags")
    @flag("quiet", "-q")
    def tags(*, quiet: bool = False) -> None:
        calls.append(f"tags {quiet}")

    notes.add(tags)

    @command("add")
    def add() -> None:
        calls.append("add")

    tags.add(add)

    result = run(notes, ["tags", "add", "-q"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: -q belongs to 'notes' and 'tags'. "
        "Write it right after the one you mean.\n"
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["lst"], "'lst' isn't a notes command. Did you mean 'list'?"),
        (["xyz"], "'xyz' isn't a notes command."),
        (["tags", "lst"], "'lst' isn't a notes tags command. Did you mean 'list'?"),
        (["tags", "xyz"], "'xyz' isn't a notes tags command."),
    ],
)
def test_unknown_command_is_reported(args: list[str], message: str) -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @command("list")
    def list_notes() -> None:
        calls.append("list notes")

    notes.add(list_notes)

    @command("add")
    def add() -> None:
        calls.append("add")

    notes.add(add)

    @group("tags")
    def tags() -> None:
        calls.append("tags")

    notes.add(tags)

    @command("list")
    def list_tags() -> None:
        calls.append("list tags")

    tags.add(list_tags)

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == f"error: {message}\n"
    assert calls == []


def test_nothing_is_checked_after_an_unknown_command() -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @command("list")
    def list_notes() -> None:
        calls.append("list")

    notes.add(list_notes)

    result = run(notes, ["lst", "--bogus", "-z", "extra", "--limit=ten"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: 'lst' isn't a notes command. Did you mean 'list'?\n"
    )
    assert calls == []


def test_group_errors_before_an_unknown_command_are_reported() -> None:
    calls: list[int] = []

    @group("notes")
    @option("limit")
    def notes(limit: int = 10) -> None:
        calls.append(limit)

    @command("list")
    def list_notes() -> None:
        calls.append(0)

    notes.add(list_notes)

    result = run(notes, ["--limit", "ten", "lst"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: --limit: 'ten' isn't a whole number.\n"
        "error: 'lst' isn't a notes command. Did you mean 'list'?\n"
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "'notes' needs a command."),
        (["-q"], "'notes' needs a command."),
        (["tags"], "'notes tags' needs a command."),
        (["due-soon"], "'notes due-soon' needs a command."),
    ],
)
def test_missing_command_is_reported(args: list[str], message: str) -> None:
    calls: list[str] = []

    @group("notes")
    @flag("quiet", "-q")
    def notes(*, quiet: bool = False) -> None:
        calls.append(f"notes {quiet}")

    @group("tags")
    def tags() -> None:
        calls.append("tags")

    notes.add(tags)

    @command("add")
    def add_tag() -> None:
        calls.append("add tag")

    tags.add(add_tag)

    @group("due_soon")
    def due_soon() -> None:
        calls.append("due soon")

    notes.add(due_soon)

    @command("list")
    def list_due() -> None:
        calls.append("list due")

    due_soon.add(list_due)

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == f"error: {message}\n"
    assert calls == []


@pytest.mark.parametrize(
    ("args", "written"),
    [
        (["--bogus", "add", "milk"], "--bogus"),
        (["--bogus", "value", "add", "milk"], "--bogus"),
        (["-x", "add", "milk"], "-x"),
        (["-x", "value", "add", "milk"], "-x"),
    ],
)
def test_unknown_group_option_takes_a_value_unless_a_command_follows(
    args: list[str], written: str
) -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @command("add")
    @argument("text")
    def add(text: str) -> None:
        calls.append(text)

    notes.add(add)

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == f"error: unknown option '{written}'.\n"
    assert calls == []


def test_double_dash_before_the_command_makes_later_options_words() -> None:
    @group("notes")
    def notes() -> None:
        pass

    @command("add")
    @argument("text")
    def add(text: str) -> str:
        return text

    notes.add(add)

    result = run(notes, ["--", "add", "-x"])

    assert result.returncode == 0
    assert result.stdout == "-x\n"
    assert result.stderr == ""


def test_group_callback_returning_a_value_raises_type_error() -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> str:
        calls.append("notes")
        return "done"

    @command("add")
    def add() -> None:
        calls.append("add")

    notes.add(add)

    message = "group 'notes' must return None, but it returned a value of type str."
    with pytest.raises(TypeError, match=re.escape(message)):
        _ = run(notes, ["add"])
    assert calls == ["notes"]


def test_running_a_nested_command_directly_skips_its_groups() -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @group("tags")
    def tags() -> None:
        calls.append("tags")

    notes.add(tags)

    @command("add")
    @argument("name")
    def add(name: str) -> None:
        calls.append(name)

    tags.add(add)

    result = run(add, ["urgent"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert calls == ["urgent"]


def test_running_a_nested_command_directly_knows_no_group_options() -> None:
    calls: list[str] = []

    @group("notes")
    @flag("quiet", "-q")
    def notes(*, quiet: bool = False) -> None:
        calls.append(f"notes {quiet}")

    @command("add")
    @argument("text")
    def add(text: str) -> None:
        calls.append(text)

    notes.add(add)

    result = run(add, ["-q", "milk"])

    assert result.returncode == 2
    assert result.stderr == "error: unknown option '-q'.\n"
    assert calls == []


def test_running_a_nested_group_directly_names_only_that_group() -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        calls.append("notes")

    @group("tags")
    def tags() -> None:
        calls.append("tags")

    notes.add(tags)

    @command("add")
    def add() -> None:
        calls.append("add")

    tags.add(add)

    result = run(tags, [])

    assert result.returncode == 2
    assert result.stderr == "error: 'tags' needs a command.\n"
    assert calls == []


def test_validate_accepts_a_valid_nested_tree() -> None:
    calls: list[str] = []

    @group("notes")
    @flag("quiet", "-q")
    def notes(*, quiet: bool = False) -> None:
        calls.append(f"notes {quiet}")

    @group("tags")
    @option("color")
    def tags(color: str = "red") -> None:
        calls.append(color)

    notes.add(tags)

    @command("add")
    @argument("name")
    def add(name: str) -> None:
        calls.append(name)

    tags.add(add)

    validate(notes)

    assert calls == []


def test_validate_checks_a_nested_command() -> None:
    @group("notes")
    def notes() -> None:
        pass

    @command("list")
    def list_notes() -> None:
        pass

    notes.add(list_notes)

    @group("tags")
    def tags() -> None:
        pass

    notes.add(tags)

    @command("add")
    def add(name: str) -> str:
        return name

    tags.add(add)

    message = "parameter 'name' has no parent."
    with pytest.raises(TypeError, match=re.escape(message)) as excinfo:
        validate(notes)
    assert excinfo.value.__notes__[0].startswith(
        f"in command 'add', defined at {__file__}:"
    )


def test_validate_checks_a_nested_group() -> None:
    calls: list[bool] = []

    @group("notes")
    def notes() -> None:
        pass

    @group("tags")
    @option("every")
    def tags(*, every: bool = False) -> None:
        calls.append(every)

    notes.add(tags)

    @command("add")
    def add() -> None:
        pass

    tags.add(add)

    message = "parameter 'every' is a bool. Use @flag(\"every\")."
    with pytest.raises(TypeError, match=re.escape(message)) as excinfo:
        validate(notes)
    assert excinfo.value.__notes__[0].startswith(
        f"in group 'tags', defined at {__file__}:"
    )


def test_run_checks_only_the_commands_on_its_command_line() -> None:
    @group("notes")
    def notes() -> None:
        pass

    @command("list")
    def list_notes() -> str:
        return "nothing yet"

    notes.add(list_notes)

    @command("add")
    def add(name: str) -> str:
        return name

    notes.add(add)

    result = run(notes, ["list"])

    assert result.returncode == 0
    assert result.stdout == "nothing yet\n"


def test_unknown_group_option_close_to_a_flag_leaves_the_command_word_alone() -> None:
    @group("notes")
    @flag("verbose", "-v")
    def notes(*, verbose: bool = False) -> None:
        _ = verbose

    @command("list")
    def list_notes() -> str:
        return "notes"

    notes.add(list_notes)

    result = run(notes, ["--verbos", "lst"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        (
            "error: unknown option '--verbos'. Did you mean '--verbose'?\n"
            "error: 'lst' isn't a notes command. Did you mean 'list'?\n"
        ),
    )


@pytest.mark.parametrize("word", ["-l5", "-lfoo"])
def test_command_option_with_an_attached_value_before_the_command(word: str) -> None:
    @group("notes")
    def notes() -> None: ...

    @command("list")
    @option("limit", "-l")
    def list_notes(limit: int = 10) -> str:
        return str(limit)

    notes.add(list_notes)

    result = run(notes, [word, "list"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: -l belongs to 'list'. Write it right after 'list'.\n",
    )


def test_errors_are_listed_node_by_node_from_the_top() -> None:
    @group("notes")
    @option("limit")
    def notes(limit: int = 1) -> None:
        _ = limit

    @command("add")
    @argument("text")
    def add(text: str) -> str:
        return text

    notes.add(add)

    result = run(notes, ["--limit", "ten", "add"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --limit: 'ten' isn't a whole number.\nerror: TEXT is required.\n",
    )


def test_add_takes_several_nodes_and_keeps_their_order() -> None:
    @group("notes")
    def notes() -> None: ...

    @command("list")
    def list_notes() -> str:
        return "listed"

    @command("add")
    def add() -> str:
        return "added"

    @group("tags")
    def tags() -> None: ...

    notes.add(list_notes, add, tags)

    assert list(notes.commands) == ["list", "add", "tags"]
    assert run(notes, ["add"]).stdout == "added\n"


def test_one_command_can_be_added_to_several_groups() -> None:
    @command("version")
    def version() -> str:
        return "1.0"

    @group("notes")
    def notes() -> None: ...

    @group("tasks")
    def tasks() -> None: ...

    notes.add(version)
    tasks.add(version)

    assert run(notes, ["version"]).stdout == "1.0\n"
    assert run(tasks, ["version"]).stdout == "1.0\n"
