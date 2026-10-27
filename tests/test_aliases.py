import re
from collections.abc import Callable

import pytest

from cliron import Context, command, group
from cliron.testing import run

Root = Callable[..., object]

ROOTS = pytest.mark.parametrize(
    ("root", "kind"), [(command, "command"), (group, "group")], ids=["command", "group"]
)


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@group("notes")
def notes() -> None:
    """Keep notes."""


@command("list", aliases="ls")
def list_notes(ctx: Context) -> str:
    """List notes."""
    return " ".join(ctx.path)


@command("remove", aliases=["rm", "delete_all"])
def remove(ctx: Context) -> str:
    """Remove a note."""
    return " ".join(ctx.path)


@group("tags", aliases="t")
def tags() -> None:
    """Work with tags."""


@command("rename")
def rename(ctx: Context) -> str:
    """Rename a tag."""
    return " ".join(ctx.path)


tags.add(rename)
notes.add(list_notes, remove, tags)


@pytest.mark.parametrize(
    ("args", "path"),
    [
        (["list"], "notes list"),
        (["ls"], "notes list"),
        (["remove"], "notes remove"),
        (["rm"], "notes remove"),
        (["delete-all"], "notes remove"),
        (["t", "rename"], "notes tags rename"),
    ],
)
def test_an_alias_runs_the_command_under_its_real_name(
    args: list[str], path: str
) -> None:
    result = run(notes, args)

    assert result.returncode == 0
    assert result.stdout == f"{path}\n"


def test_help_lists_aliases_next_to_the_name() -> None:
    assert run(notes, ["--help"]).stdout == (
        "Usage: notes [OPTIONS] COMMAND\n"
        "\n"
        "Keep notes.\n"
        "\n"
        "Options:\n"
        "  -h, --help            Show this help and exit.\n"
        "\n"
        "Commands:\n"
        "  list, ls              List notes.\n"
        "  remove, rm, delete-all\n"
        "                        Remove a note.\n"
        "  tags, t               Work with tags.\n"
    )


def test_help_and_errors_through_an_alias_use_the_real_name() -> None:
    assert run(notes, ["ls", "-h"]).stdout.startswith("Usage: notes list [OPTIONS]\n")
    assert run(notes, ["ls", "--bad"]).stderr == (
        "error: unknown option '--bad'.\nRun 'notes list --help' for usage.\n"
    )


def test_suggestions_include_aliases() -> None:
    assert run(notes, ["lss"]).stderr.startswith(
        "error: 'lss' isn't a notes command. Did you mean 'ls'?\n"
    )


def test_an_alias_after_an_unknown_option_is_still_the_command() -> None:
    assert run(notes, ["--nope", "ls"]).stderr == (
        "error: unknown option '--nope'.\nRun 'notes list --help' for usage.\n"
    )


@ROOTS
@pytest.mark.parametrize("aliases", [3, None, ["ls", 3]])
def test_aliases_must_be_a_name_or_a_list_of_names(
    root: Root, kind: str, aliases: object
) -> None:
    message = (
        f"@{kind} takes aliases as a name or a list of names, "
        f"such as 'ls' or ['ls', 'l'], not {aliases!r}."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = root("list", aliases=aliases)


@ROOTS
@pytest.mark.parametrize(
    ("aliases", "message"),
    [
        ("LS", "'LS' isn't snake_case. Use 'ls'."),
        (
            ["ls", "list"],
            "'list' is already the {kind}'s name. Remove it from aliases.",
        ),
        (["ls", "l", "ls"], "aliases of @{kind} lists 'ls' twice. Remove one."),
    ],
)
def test_wrong_aliases_are_rejected(
    root: Root, kind: str, aliases: str | list[str], message: str
) -> None:
    with pytest.raises(ValueError, match=exactly(message.format(kind=kind))):
        _ = root("list", aliases=aliases)


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [
        (
            ("list", "ls"),
            ("ls", ()),
            (
                "group 'cli' already uses 'ls' as an alias of 'list'. "
                "Rename one of them or remove the alias."
            ),
        ),
        (
            ("ls", ()),
            ("list", "ls"),
            (
                "group 'cli' already has a command 'ls', so it can't be an alias of "
                "'list'. Remove the alias or rename the command."
            ),
        ),
        (
            ("list", "ls"),
            ("logs", ["lg", "ls"]),
            (
                "group 'cli' already uses 'ls' as an alias of 'list', so it can't be "
                "an alias of 'logs'. Remove one of them."
            ),
        ),
    ],
)
def test_a_group_rejects_a_name_or_alias_that_is_taken(
    first: tuple[str, str | tuple[str, ...]],
    second: tuple[str, str | list[str] | tuple[str, ...]],
    message: str,
) -> None:
    @group("cli")
    def cli() -> None: ...

    def items() -> None: ...

    cli.add(command(first[0], aliases=first[1])(items))
    with pytest.raises(ValueError, match=exactly(message)):
        cli.add(group(second[0], aliases=second[1])(items))


def test_groups_can_use_the_same_alias() -> None:
    @group("cli")
    def cli() -> None: ...

    @group("tags")
    def tag_group() -> None: ...

    def items() -> str:
        return "ran"

    tag_group.add(command("list", aliases="ls")(items))
    cli.add(command("list", aliases="ls")(items), tag_group)

    assert run(cli, ["ls"]).stdout == "ran\n"
    assert run(cli, ["tags", "ls"]).stdout == "ran\n"
