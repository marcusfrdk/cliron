import os
import re
import sys
from collections.abc import Callable
from datetime import date, datetime, time
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Literal

import pytest

from cliron import (
    argument,
    between,
    choices,
    command,
    dependency,
    env,
    flag,
    group,
    length,
    matches,
    option,
    stdin,
)
from cliron.testing import run, validate

Check = Callable[..., object]
Root = Callable[..., object]

NOTES_PATH = Path("notes.txt")
FOLDERS = ["inbox", "done"]

CHECKS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)
NESTED_CHECKS = pytest.mark.parametrize(
    "check",
    [validate, partial(run, args=["tags", "add"])],
    ids=["validate", "run"],
)
ROOTS = pytest.mark.parametrize(
    ("root", "kind"), [(command, "command"), (group, "group")], ids=["command", "group"]
)

HELP_FIX = " Use another flag, or choose other help_flags."
VERSION_FIX = " Use another flag for the option."
SHARED_FIX = " Leave --version out of help_flags."

FLAG_RULE = (
    "Use a dash and one letter, such as '-h', "
    "or two dashes and a kebab-case name, such as '--help'."
)
TEXT_HELP = "Only show notes whose title or body has the text, case-insensitively."
CREATED_HELP = (
    "Only show notes created after this date and time, in your local time zone."
)


class Priority(Enum):
    LOW = "low"
    NORMAL = "normal"
    VERY_HIGH = "very high"


class Level(Enum):
    LOW = "low"
    HIGH = "high"


HIGH_LEVELS = [Level.HIGH]


@group("notes")
@flag("quiet", "-q", help="Print less.")
def notes_group(*, quiet: bool = False) -> None:
    """
    Keep notes in the terminal.

    Notes are kept in a plain text file.
    """
    _ = quiet


def list_every_note() -> None:
    pass


list_every_note.__doc__ = """
    List every note,
    newest first.

    :returns: Nothing.
    """
notes_list = command("list")(list_every_note)


@command("add")
@argument("title", help="The note's title.")
@option("count", "-c", help="How many copies to add.")
def notes_add(title: str, count: int = 1) -> str:
    """Add a note."""
    return f"{title} x{count}"


@group("tags")
@option("color", help="The color of new tags.")
def tags_group(color: str = "red") -> None:
    """Manage tags."""
    _ = color


@command("add")
@argument("name")
def tags_add(name: str) -> str:
    return name


@command("remove_duplicates")
def notes_remove_duplicates() -> None:
    pass


notes_group.add(notes_list, notes_add, tags_group, notes_remove_duplicates)
tags_group.add(tags_add)


@command("find")
@option("text", "-t", help=TEXT_HELP)
@flag("archived", help="Show archived notes too.")
def find_notes(text: str | None = None, *, archived: bool = False) -> None:
    """Find notes."""
    _ = (text, archived)


@command("find")
def search_notes() -> None:
    """
    Find notes whose title, body or tags match the text, and print them newest first.

    :returns: Nothing.
    """


@command("show")
@flag("short", "-s", help="Print one line per note.")
def show_notes(*, short: bool = False) -> str:
    return "short" if short else "long"


NOTES_HELP = """\
Usage: notes [OPTIONS] COMMAND

Keep notes in the terminal.

Options:
  -q, --quiet        Print less.
  -h, --help         Show this help and exit.

Commands:
  list               List every note,
  add                Add a note.
  tags               Manage tags.
  remove-duplicates
"""

NOTES_LIST_HELP = """\
Usage: notes [OPTIONS] list [OPTIONS]

List every note, newest first.

Options:
  -h, --help   Show this help and exit.

Options for notes:
  -q, --quiet  Print less.
"""

NOTES_ADD_HELP = """\
Usage: notes [OPTIONS] add [OPTIONS] TITLE

Add a note.

Arguments:
  TITLE            The note's title.

Options:
  -c, --count INT  How many copies to add. (default: 1)
  -h, --help       Show this help and exit.

Options for notes:
  -q, --quiet      Print less.
"""

TAGS_HELP = """\
Usage: notes [OPTIONS] tags [OPTIONS] COMMAND

Manage tags.

Options:
  --color TEXT  The color of new tags. (default: red)
  -h, --help    Show this help and exit.

Options for notes:
  -q, --quiet   Print less.

Commands:
  add
"""

TAGS_ADD_HELP = """\
Usage: notes [OPTIONS] tags [OPTIONS] add [OPTIONS] NAME

Arguments:
  NAME

Options:
  -h, --help    Show this help and exit.

Options for notes:
  -q, --quiet   Print less.

Options for notes tags:
  --color TEXT  The color of new tags. (default: red)
"""

FIND_HELP = """\
Usage: find [OPTIONS]

Find notes.

Options:
  -t, --text TEXT  Only show notes whose title or body has the text,
                   case-insensitively.
  --archived       Show archived notes too.
  -h, --help       Show this help and exit.
"""

FIND_HELP_50 = """\
Usage: find [OPTIONS]

Find notes.

Options:
  -t, --text TEXT  Only show notes whose title
                   or body has the text,
                   case-insensitively.
  --archived       Show archived notes too.
  -h, --help       Show this help and exit.
"""

FIND_HELP_30 = """\
Usage: find [OPTIONS]

Find notes.

Options:
  -t, --text TEXT
        Only show notes
        whose title or body
        has the text,
        case-insensitively.
  --archived
        Show archived notes
        too.
  -h, --help
        Show this help and
        exit.
"""

FIND_HELP_24 = """\
Usage: find [OPTIONS]

Find notes.

Options:
  -t, --text TEXT
    Only show notes
    whose title or
    body has the text,
    case-insensitively.
  --archived
    Show archived
    notes too.
  -h, --help
    Show this help and
    exit.
"""

FIND_HELP_16_TAIL = """

Find notes.

Options:
  -t, --text TEXT
    Only show
    notes whose
    title or
    body has
    the text,
    case-insensitively.
  --archived
    Show
    archived
    notes too.
  -h, --help
    Show this
    help and
    exit.
"""

SEARCH_HELP = """\
Usage: find [OPTIONS]

Find notes whose title, body or tags match the text, and print them newest
first.

Options:
  -h, --help  Show this help and exit.
"""

SEARCH_HELP_50 = """\
Usage: find [OPTIONS]

Find notes whose title, body or tags match the
text, and print them newest first.

Options:
  -h, --help  Show this help and exit.
"""

VERSIONED_NOTES_HELP = """\
Usage: notes [OPTIONS] COMMAND

Keep notes.

Options:
  --version   Show the version and exit.
  -h, --help  Show this help and exit.

Commands:
  add         Add a note.
"""

VERSIONED_ADD_HELP = """\
Usage: notes add [OPTIONS]

Add a note.

Options:
  --version   Show the version and exit.
  -h, --help  Show this help and exit.
"""

SHOW_HELP = """\
Usage: show [OPTIONS]

Options:
  -s, --short  Print one line per note.
  -h, --help   Show this help and exit.
"""


@pytest.fixture(autouse=True)
def fixed_width(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLUMNS", raising=False)


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def defined_at(kind: str, name: str, line: int) -> str:
    return f"in {kind} '{name}', defined at {__file__}:{line}"


@pytest.mark.parametrize("args", [["-h"], ["--help"]])
def test_command_help_shows_usage_summary_arguments_and_options(
    args: list[str],
) -> None:
    @command("add")
    @argument("title", help="The note's title.")
    @argument("tags", help="Tags to attach.")
    @option("priority", "-p", help="How urgent the note is.")
    @option("author", "-a", help="Who wrote the note.")
    @flag("verbose", "-v", help="Print more.")
    def add(
        title: str,
        tags: list[str],
        priority: Priority = Priority.NORMAL,
        *,
        author: str,
        verbose: int = 0,
    ) -> None:
        """
        Add a note to the list.

        The note is saved right away.

        :param title: The note's title.
        :param tags: Tags to attach.
        """
        _ = (title, tags, priority, author, verbose)

    expected = """\
Usage: add [OPTIONS] TITLE TAGS...

Add a note to the list.

Arguments:
  TITLE                 The note's title.
  TAGS...               Tags to attach. Repeatable.

Options:
  -p, --priority [low|normal|very-high]
                        How urgent the note is. (default: normal)
  -a, --author TEXT     Who wrote the note. (required)
  -v, --verbose         Print more. Repeatable.
  -h, --help            Show this help and exit.
"""

    result = run(add, args)

    assert result.returncode == 0
    assert result.stdout == expected
    assert result.stderr == ""


def test_help_shows_a_placeholder_for_each_scalar_type() -> None:
    @command("show")
    @option("text")
    @option("count")
    @option("ratio")
    @option("path")
    @option("day")
    def show(
        text: str | None = None,
        count: int | None = None,
        ratio: float | None = None,
        path: Path | None = None,
        day: date | None = None,
    ) -> None:
        _ = (text, count, ratio, path, day)

    expected = """\
Usage: show [OPTIONS]

Options:
  --text TEXT
  --count INT
  --ratio FLOAT
  --path PATH
  --day DATE
  -h, --help     Show this help and exit.
"""

    result = run(show, ["--help"])

    assert result.stdout == expected


def test_help_shows_placeholders_for_times_choices_and_lists() -> None:
    @command("show")
    @option("moment")
    @option("clock")
    @option("level")
    @option("mode")
    @option("tags")
    def show(
        moment: datetime | None = None,
        clock: time | None = None,
        level: Priority | None = None,
        mode: Literal["fast", "safe"] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        _ = (moment, clock, level, mode, tags)

    expected = """\
Usage: show [OPTIONS]

Options:
  --moment DATETIME
  --clock TIME
  --level [low|normal|very-high]
  --mode [fast|safe]
  --tags TEXT           Repeatable.
  -h, --help            Show this help and exit.
"""

    result = run(show, ["--help"])

    assert result.stdout == expected


def test_help_shows_scalar_defaults() -> None:
    @command("export")
    @option("count", "-c", help="How many notes.")
    @option("title")
    @option("prefix", help="Text before each note.")
    @option("path")
    @option("level")
    def export(
        count: int = 3,
        title: str = "Notes",
        prefix: str = "",
        path: Path = NOTES_PATH,
        level: Priority = Priority.VERY_HIGH,
    ) -> None:
        _ = (count, title, prefix, path, level)

    expected = """\
Usage: export [OPTIONS]

Options:
  -c, --count INT       How many notes. (default: 3)
  --title TEXT          (default: Notes)
  --prefix TEXT         Text before each note. (default: '')
  --path PATH           (default: notes.txt)
  --level [low|normal|very-high]
                        (default: very-high)
  -h, --help            Show this help and exit.
"""

    result = run(export, ["--help"])

    assert result.stdout == expected


def test_help_shows_collection_defaults_but_not_none_or_flags() -> None:
    @command("sync")
    @option("tags", "-t", help="Tags to sync.")
    @option("limit", help="Stop after this many.")
    @option("labels")
    @flag("dry_run", "-n", help="Only show what would change.")
    @flag("verbose", "-v")
    def sync(
        tags: tuple[str, ...] = ("work", "home"),
        limit: int | None = None,
        labels: tuple[str, ...] = (),
        *,
        dry_run: bool = False,
        verbose: int = 0,
    ) -> None:
        _ = (tags, limit, labels, dry_run, verbose)

    expected = """\
Usage: sync [OPTIONS]

Options:
  -t, --tags TEXT  Tags to sync. Repeatable. (default: work, home)
  --limit INT      Stop after this many.
  --labels TEXT    Repeatable.
  -n, --dry-run    Only show what would change.
  -v, --verbose    Repeatable.
  -h, --help       Show this help and exit.
"""

    result = run(sync, ["--help"])

    assert result.stdout == expected


def test_help_shows_optional_arguments_and_required_options() -> None:
    @command("copy")
    @argument("source", help="The note to copy.")
    @argument("target")
    @argument("folders", help="Copy into these.")
    @option("mode", "-m", help="How to copy.")
    @option("owner", help="Who owns the copies.")
    def copy(
        source: str,
        target: Path = NOTES_PATH,
        folders: list[str] = FOLDERS,
        mode: Literal["fast", "safe"] = "safe",
        *,
        owner: str,
    ) -> None:
        _ = (source, target, folders, mode, owner)

    expected = """\
Usage: copy [OPTIONS] SOURCE [TARGET] [FOLDERS...]

Arguments:
  SOURCE                The note to copy.
  TARGET                (default: notes.txt)
  FOLDERS...            Copy into these. Repeatable. (default: inbox, done)

Options:
  -m, --mode [fast|safe]
                        How to copy. (default: safe)
  --owner TEXT          Who owns the copies. (required)
  -h, --help            Show this help and exit.
"""

    result = run(copy, ["--help"])

    assert result.stdout == expected


def test_arguments_with_choices_show_them_after_the_placeholder() -> None:
    @command("set")
    @argument("level", help="How urgent the note is.")
    @argument("mode", help="How to save the note.")
    @argument("speed")
    @argument("levels", help="Levels to allow as well.")
    def set_level(
        level: Level,
        mode: Literal["fast", "safe"],
        speed: Literal["slow", "quick"] = "slow",
        levels: list[Level] = HIGH_LEVELS,
    ) -> None:
        _ = (level, mode, speed, levels)

    expected = """\
Usage: set [OPTIONS] LEVEL MODE [SPEED] [LEVELS...]

Arguments:
  LEVEL [low|high]      How urgent the note is.
  MODE [fast|safe]      How to save the note.
  SPEED [slow|quick]    (default: slow)
  LEVELS... [low|high]  Levels to allow as well. Repeatable. (default: high)

Options:
  -h, --help            Show this help and exit.
"""

    result = run(set_level, ["--help"])

    assert result.stdout == expected


def test_usage_shows_only_the_placeholder_of_an_argument_with_choices() -> None:
    @group("notes")
    @flag("quiet", "-q", help="Print less.")
    def notes(*, quiet: bool = False) -> None:
        _ = quiet

    @group("tags")
    @option("color", help="The color of new tags.")
    def tags(color: str = "red") -> None:
        _ = color

    @command("set")
    @argument("level")
    @argument("mode")
    def set_level(level: Level, mode: Literal["fast", "safe"] = "safe") -> None:
        _ = (level, mode)

    notes.add(tags)
    tags.add(set_level)

    expected = """\
Usage: notes [OPTIONS] tags [OPTIONS] set [OPTIONS] LEVEL [MODE]

Arguments:
  LEVEL [low|high]
  MODE [fast|safe]  (default: safe)

Options:
  -h, --help        Show this help and exit.

Options for notes:
  -q, --quiet       Print less.

Options for notes tags:
  --color TEXT      The color of new tags. (default: red)
"""

    result = run(notes, ["tags", "set", "--help"])

    assert result.stdout == expected


def test_required_list_option_is_repeatable_and_required() -> None:
    @command("tag")
    @option("names", "-n", help="The tags.")
    def tag(names: list[str]) -> None:
        _ = names

    expected = """\
Usage: tag [OPTIONS]

Options:
  -n, --names TEXT  The tags. Repeatable. (required)
  -h, --help        Show this help and exit.
"""

    result = run(tag, ["--help"])

    assert result.stdout == expected


@pytest.mark.parametrize(
    ("decorator", "args"),
    [
        (argument, ("title", "The note's title.")),
        (option, ("title", "-t", "The note's title.")),
        (flag, ("quiet", "-q", "Print less.")),
    ],
    ids=["argument", "option", "flag"],
)
def test_help_text_is_keyword_only(
    decorator: Callable[..., object], args: tuple[str, ...]
) -> None:
    with pytest.raises(TypeError, match="positional argument"):
        _ = decorator(*args)


def test_help_column_is_shared_by_all_sections() -> None:
    @command("move")
    @argument("destination", help="Where to move the notes.")
    def move(destination: Path) -> None:
        _ = destination

    expected = """\
Usage: move [OPTIONS] DESTINATION

Arguments:
  DESTINATION  Where to move the notes.

Options:
  -h, --help   Show this help and exit.
"""

    result = run(move, ["--help"])

    assert result.stdout == expected


def test_long_names_go_on_their_own_line() -> None:
    @command("find")
    @option("created_after", help=CREATED_HELP)
    @option("remind_at", help="Remind me at this moment.")
    @option("remind_earlier", help="Remind me this long before.")
    @option("tag", "-t", help="Only show notes with this tag.")
    def find(
        created_after: datetime | None = None,
        remind_at: datetime | None = None,
        remind_earlier: time | None = None,
        tag: str | None = None,
    ) -> None:
        _ = (created_after, remind_at, remind_earlier, tag)

    expected = """\
Usage: find [OPTIONS]

Options:
  --created-after DATETIME
                        Only show notes created after this date and time, in
                        your local time zone.
  --remind-at DATETIME  Remind me at this moment.
  --remind-earlier TIME
                        Remind me this long before.
  -t, --tag TEXT        Only show notes with this tag.
  -h, --help            Show this help and exit.
"""

    result = run(find, ["--help"])

    assert result.stdout == expected


def test_help_wraps_at_78_columns_without_breaking_hyphens() -> None:
    result = run(find_notes, ["--help"])

    assert result.stdout == FIND_HELP


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        ("200", FIND_HELP),
        ("80", FIND_HELP),
        ("50", FIND_HELP_50),
        ("30", FIND_HELP_30),
        ("24", FIND_HELP_24),
    ],
)
def test_columns_sets_the_width_up_to_80(
    columns: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", columns)

    result = run(find_notes, ["--help"])

    assert result.stdout == expected


def test_help_text_is_at_least_11_columns_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLUMNS", "16")

    result = run(find_notes, ["--help"])

    assert result.stdout.endswith(FIND_HELP_16_TAIL)


@pytest.mark.parametrize("columns", ["wide", "0", "-50", ""])
def test_columns_that_isnt_a_positive_integer_is_ignored(
    columns: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", columns)

    result = run(find_notes, ["--help"])

    assert result.stdout == FIND_HELP


@pytest.mark.parametrize(
    ("columns", "expected"), [("80", SEARCH_HELP), ("50", SEARCH_HELP_50)]
)
def test_summary_wraps_at_the_width(
    columns: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", columns)

    result = run(search_notes, ["--help"])

    assert result.stdout == expected


@pytest.mark.parametrize("args", [["-h"], ["--help"]])
def test_group_help_lists_commands_in_the_order_they_were_added(
    args: list[str],
) -> None:
    result = run(notes_group, args)

    assert result.returncode == 0
    assert result.stdout == NOTES_HELP
    assert result.stderr == ""


def test_group_without_docstring_has_no_summary() -> None:
    @group("archive")
    def archive() -> None:
        pass

    @command("restore")
    @argument("name")
    def restore(name: str) -> str:
        """Restore a note."""
        return name

    archive.add(restore)

    expected = """\
Usage: archive [OPTIONS] COMMAND

Options:
  -h, --help  Show this help and exit.

Commands:
  restore     Restore a note.
"""

    result = run(archive, ["--help"])

    assert result.stdout == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-h", "add"], NOTES_HELP),
        (["add", "-h"], NOTES_ADD_HELP),
        (["list", "--help"], NOTES_LIST_HELP),
        (["-h", "tags", "add"], NOTES_HELP),
        (["tags", "-h", "add", "urgent"], TAGS_HELP),
        (["tags", "add", "--help"], TAGS_ADD_HELP),
        (["-h", "tags", "--help"], TAGS_HELP),
        (["tags", "--help", "add", "-h"], TAGS_ADD_HELP),
        (["-qh", "list"], NOTES_HELP),
        (["-h", "zzz"], NOTES_HELP),
    ],
)
def test_help_is_for_the_segment_the_flag_is_written_in(
    args: list[str], expected: str
) -> None:
    result = run(notes_group, args)

    assert result.returncode == 0
    assert result.stdout == expected
    assert result.stderr == ""


def test_help_before_a_bare_nested_group_shows_the_outer_help() -> None:
    result = run(notes_group, ["-h", "tags"])

    assert result.returncode == 0
    assert result.stdout == NOTES_HELP
    assert result.stderr == ""


def test_command_help_lists_each_enclosing_groups_options_in_path_order() -> None:
    @group("notes")
    @option("store", "-s", help="Where notes are kept.")
    @flag("quiet", "-q", help="Print less.")
    def notes(store: Path = NOTES_PATH, *, quiet: bool = False) -> None:
        _ = (store, quiet)

    @group("tags")
    @option("color", help="The color of new tags.")
    def tags(color: str = "red") -> None:
        _ = color

    @command("set")
    @argument("name", help="The tag to set.")
    @option("level", "-l", help="How important the tag is.")
    def set_tag(name: str, level: int = 1) -> None:
        """Set a tag on the newest note."""
        _ = (name, level)

    notes.add(tags)
    tags.add(set_tag)

    expected = """\
Usage: notes [OPTIONS] tags [OPTIONS] set [OPTIONS] NAME

Set a tag on the newest note.

Arguments:
  NAME              The tag to set.

Options:
  -l, --level INT   How important the tag is. (default: 1)
  -h, --help        Show this help and exit.

Options for notes:
  -s, --store PATH  Where notes are kept. (default: notes.txt)
  -q, --quiet       Print less.

Options for notes tags:
  --color TEXT      The color of new tags. (default: red)
"""

    result = run(notes, ["tags", "set", "--help"])

    assert result.returncode == 0
    assert result.stdout == expected
    assert result.stderr == ""


def test_group_without_options_gets_no_section_or_usage_placeholder() -> None:
    @group("notes")
    @flag("quiet", "-q", help="Print less.")
    def notes(*, quiet: bool = False) -> None:
        _ = quiet

    @group("tags")
    def tags() -> None:
        """Manage tags."""

    @group("colors")
    @option("palette", help="The palette to pick from.")
    def colors(palette: str = "basic") -> None:
        _ = palette

    @command("set")
    @argument("color")
    def set_color(color: str) -> None:
        _ = color

    notes.add(tags)
    tags.add(colors)
    colors.add(set_color)

    expected = """\
Usage: notes [OPTIONS] tags colors [OPTIONS] set [OPTIONS] COLOR

Arguments:
  COLOR

Options:
  -h, --help      Show this help and exit.

Options for notes:
  -q, --quiet     Print less.

Options for notes tags colors:
  --palette TEXT  The palette to pick from. (default: basic)
"""

    result = run(notes, ["tags", "colors", "set", "--help"])

    assert result.stdout == expected


def test_nested_group_help_lists_the_outer_groups_options_before_commands() -> None:
    @group("notes")
    @option("store", "-s", help="Where notes are kept.")
    def notes(store: Path = NOTES_PATH) -> None:
        """Keep notes."""
        _ = store

    @group("tags")
    @flag("archived", "-a", help="Include archived tags.")
    def tags(*, archived: bool = False) -> None:
        """Manage tags."""
        _ = archived

    @command("add")
    def add_tag() -> None:
        """Add a tag."""

    @command("remove")
    def remove_tag() -> None:
        """Remove a tag."""

    notes.add(tags)
    tags.add(add_tag, remove_tag)

    expected = """\
Usage: notes [OPTIONS] tags [OPTIONS] COMMAND

Manage tags.

Options:
  -a, --archived    Include archived tags.
  -h, --help        Show this help and exit.

Options for notes:
  -s, --store PATH  Where notes are kept. (default: notes.txt)

Commands:
  add               Add a tag.
  remove            Remove a tag.
"""

    result = run(notes, ["tags", "--help"])

    assert result.stdout == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ["tags", "rename", "--help"],
            """\
Usage: notes [OPTIONS] tags [OPTIONS] rename [OPTIONS] OLD NEW

Rename one.

Arguments:
  OLD
  NEW

Options:
  -h, --help    Show this help and exit.

Options for notes:
  -q, --quiet   Print less.

Options for notes tags:
  --color TEXT  The color of new tags. (default: red)
""",
        ),
        (
            ["folders", "rename", "--help"],
            """\
Usage: notes [OPTIONS] folders [OPTIONS] rename [OPTIONS] OLD NEW

Rename one.

Arguments:
  OLD
  NEW

Options:
  -h, --help         Show this help and exit.

Options for notes:
  -q, --quiet        Print less.

Options for notes folders:
  -p, --parent TEXT  The folder to work in. (default: inbox)
""",
        ),
    ],
    ids=["tags", "folders"],
)
def test_shared_command_help_shows_the_path_it_was_reached_by(
    args: list[str], expected: str
) -> None:
    @group("notes")
    @flag("quiet", "-q", help="Print less.")
    def notes(*, quiet: bool = False) -> None:
        _ = quiet

    @group("tags")
    @option("color", help="The color of new tags.")
    def tags(color: str = "red") -> None:
        _ = color

    @group("folders")
    @option("parent", "-p", help="The folder to work in.")
    def folders(parent: str = "inbox") -> None:
        _ = parent

    @command("rename")
    @argument("old")
    @argument("new")
    def rename(old: str, new: str) -> str:
        """Rename one."""
        return f"{old} {new}"

    notes.add(tags, folders)
    tags.add(rename)
    folders.add(rename)

    result = run(notes, args)

    assert result.stdout == expected


def test_long_rows_in_a_group_section_go_on_their_own_line() -> None:
    @group("notes")
    @option("created_after", help=CREATED_HELP)
    @option("level", "-l", help="Only show notes this urgent.")
    def notes(
        created_after: datetime | None = None, level: Priority = Priority.NORMAL
    ) -> None:
        _ = (created_after, level)

    @command("list")
    @flag("short", "-s", help="Print one line per note.")
    def list_notes(*, short: bool = False) -> None:
        """List notes."""
        _ = short

    notes.add(list_notes)

    expected = """\
Usage: notes [OPTIONS] list [OPTIONS]

List notes.

Options:
  -s, --short           Print one line per note.
  -h, --help            Show this help and exit.

Options for notes:
  --created-after DATETIME
                        Only show notes created after this date and time, in
                        your local time zone.
  -l, --level [low|normal|very-high]
                        Only show notes this urgent. (default: normal)
"""

    result = run(notes, ["list", "--help"])

    assert result.stdout == expected


@pytest.mark.parametrize(
    "args",
    [
        ["add", "-h"],
        ["add", "Milk", "--count", "many", "-h"],
        ["add", "--count", "-h"],
        ["add", "Milk", "--nope", "-h"],
        ["add", "Milk", "Eggs", "-h"],
        ["add", "-h", "--count", "many"],
        ["add", "Milk", "-c", "1", "-c", "2", "--help"],
        ["--nope", "add", "-h"],
    ],
    ids=[
        "missing",
        "invalid",
        "missing-value",
        "unknown-option",
        "extra-argument",
        "help-first",
        "given-twice",
        "unknown-group-option",
    ],
)
def test_help_wins_over_input_errors(args: list[str]) -> None:
    result = run(notes_group, args)

    assert result.returncode == 0
    assert result.stdout == NOTES_ADD_HELP
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        (
            ["zzz", "-h"],
            "error: 'zzz' isn't a notes command.\nRun 'notes --help' for usage.\n",
        ),
        (
            ["tags", "zzz", "--help"],
            (
                "error: 'zzz' isn't a notes tags command.\n"
                "Run 'notes tags --help' for usage.\n"
            ),
        ),
    ],
)
def test_help_after_an_unknown_command_is_never_read(
    args: list[str], stderr: str
) -> None:
    result = run(notes_group, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == stderr


@pytest.mark.parametrize("args", [["-sh"], ["-hs"], ["--short", "-sh"]])
def test_help_flag_in_a_bundle_shows_help(args: list[str]) -> None:
    result = run(show_notes, args)

    assert result.returncode == 0
    assert result.stdout == SHOW_HELP
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("args", "flag_"),
    [
        (["--help=x"], "--help"),
        (["--help="], "--help"),
        (["-h=x"], "-h"),
        (["-sh=x"], "-h"),
    ],
)
def test_help_flag_with_a_value_is_an_error(args: list[str], flag_: str) -> None:
    result = run(show_notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: {flag_} doesn't take a value.\nRun 'show --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("args", "stdout"),
    [(["--", "-h"], "-h\n"), (["--", "--help", "-h"], "--help -h\n")],
)
def test_help_flag_after_double_dash_is_a_word(args: list[str], stdout: str) -> None:
    @command("echo")
    @argument("words")
    def echo(words: list[str]) -> str:
        return " ".join(words)

    result = run(echo, args)

    assert result.returncode == 0
    assert result.stdout == stdout
    assert result.stderr == ""


def test_help_flag_after_double_dash_is_a_command_name_for_a_group() -> None:
    result = run(notes_group, ["--", "-h"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: '-h' isn't a notes command.\nRun 'notes --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("args", "expected"),
    [([], NOTES_HELP), (["tags"], TAGS_HELP), (["-q", "tags"], TAGS_HELP)],
)
def test_group_with_nothing_after_it_prints_its_help_to_stderr(
    args: list[str], expected: str
) -> None:
    result = run(notes_group, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == expected


@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        (
            ["-q"],
            "error: 'notes' needs a command.\nRun 'notes --help' for usage.\n",
        ),
        (
            ["tags", "--color", "blue"],
            (
                "error: 'notes tags' needs a command.\n"
                "Run 'notes tags --help' for usage.\n"
            ),
        ),
    ],
)
def test_group_with_options_but_no_command_is_an_error(
    args: list[str], stderr: str
) -> None:
    result = run(notes_group, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == stderr


@pytest.mark.parametrize("help_flags", [False, []], ids=["false", "empty-list"])
@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        ([], "error: 'notes' needs a command.\n"),
        (["archive"], "error: 'notes archive' needs a command.\n"),
    ],
)
def test_group_without_help_needs_a_command(
    args: list[str], stderr: str, *, help_flags: bool | list[str]
) -> None:
    @group("notes", help_flags=help_flags)
    def notes() -> None:
        pass

    @group("archive")
    def archive() -> None:
        pass

    @command("restore")
    def restore() -> None:
        pass

    notes.add(archive)
    archive.add(restore)

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == stderr


@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        (["add"], "error: TITLE is required.\nRun 'notes add --help' for usage.\n"),
        (
            ["tags", "add"],
            "error: NAME is required.\nRun 'notes tags add --help' for usage.\n",
        ),
        (
            ["zzz"],
            "error: 'zzz' isn't a notes command.\nRun 'notes --help' for usage.\n",
        ),
        (
            ["--nope", "list"],
            "error: unknown option '--nope'.\nRun 'notes list --help' for usage.\n",
        ),
        (
            ["-q", "-q", "tags", "add", "urgent"],
            (
                "error: -q/--quiet can only be given once.\n"
                "Run 'notes tags add --help' for usage.\n"
            ),
        ),
    ],
)
def test_errors_end_with_a_usage_hint_for_the_deepest_node(
    args: list[str], stderr: str
) -> None:
    result = run(notes_group, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == stderr


@pytest.mark.parametrize(
    ("help_flags", "hint"),
    [
        (True, "--help"),
        (["--help"], "--help"),
        (["-H", "--usage"], "--usage"),
        (["--usage", "-H"], "--usage"),
        (["-H"], "-H"),
        (["-u", "-H"], "-u"),
    ],
)
def test_usage_hint_names_the_long_help_flag(
    hint: str, *, help_flags: bool | list[str]
) -> None:
    @command("greet", help_flags=help_flags)
    @argument("name")
    def greet(name: str) -> str:
        return name

    result = run(greet, [])

    assert result.returncode == 2
    assert result.stderr == f"error: NAME is required.\nRun 'greet {hint}' for usage.\n"


@pytest.mark.parametrize("help_flags", [False, []], ids=["false", "empty-list"])
@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        ([], "error: NAME is required.\n"),
        (["Ada", "-h"], "error: unknown option '-h'.\n"),
        (["Ada", "--help"], "error: unknown option '--help'.\n"),
    ],
)
def test_disabled_help_removes_the_flags_and_the_usage_hint(
    args: list[str], stderr: str, *, help_flags: bool | list[str]
) -> None:
    @command("greet", help_flags=help_flags)
    @argument("name")
    def greet(name: str) -> str:
        return name

    result = run(greet, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == stderr


@pytest.mark.parametrize("args", [["-H"], ["--usage"]])
def test_help_flags_rename_the_help_flags(args: list[str]) -> None:
    @command("add", help_flags=["-H", "--usage"])
    def add() -> None:
        """Add a note."""

    expected = """\
Usage: add [OPTIONS]

Add a note.

Options:
  -H, --usage  Show this help and exit.
"""

    result = run(add, args)

    assert result.returncode == 0
    assert result.stdout == expected
    assert result.stderr == ""


@pytest.mark.parametrize("flag_", ["-h", "--help"])
def test_renamed_help_drops_the_default_flags(flag_: str) -> None:
    @command("add", help_flags=["-H", "--usage"])
    def add() -> None:
        """Add a note."""

    result = run(add, [flag_])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: unknown option '{flag_}'.\nRun 'add --usage' for usage.\n"
    )


@pytest.mark.parametrize("args", [["-h"], ["--help"]])
def test_help_flags_true_keeps_the_default_flags(args: list[str]) -> None:
    @command("add", help_flags=True)
    def add() -> None:
        """Add a note."""

    expected = """\
Usage: add [OPTIONS]

Add a note.

Options:
  -h, --help  Show this help and exit.
"""

    result = run(add, args)

    assert result.returncode == 0
    assert result.stdout == expected


def test_renamed_help_frees_h_for_an_option() -> None:
    @command("connect", help_flags=["--help"])
    @option("host", "-h", help="The server.")
    def connect(host: str = "localhost") -> str:
        return host

    expected = """\
Usage: connect [OPTIONS]

Options:
  -h, --host TEXT  The server. (default: localhost)
  --help           Show this help and exit.
"""

    validate(connect)
    connected = run(connect, ["-h", "example.org"])
    helped = run(connect, ["--help"])

    assert (connected.returncode, connected.stdout, connected.stderr) == (
        0,
        "example.org\n",
        "",
    )
    assert helped.stdout == expected


def test_disabled_help_frees_its_flags_for_an_option() -> None:
    @command("explain", help_flags=False)
    @option("help", "-h")
    def explain(help: str = "") -> str:
        return help

    validate(explain)
    long = run(explain, ["--help", "flags"])
    short = run(explain, ["-h", "usage"])

    assert (long.returncode, long.stdout, long.stderr) == (0, "flags\n", "")
    assert (short.returncode, short.stdout, short.stderr) == (0, "usage\n", "")


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ["--usage"],
            """\
Usage: notes [OPTIONS] COMMAND

Keep notes.

Options:
  --usage  Show this help and exit.

Commands:
  add      Add a note.
  tags     Manage tags.
""",
        ),
        (
            ["add", "--usage"],
            """\
Usage: notes add [OPTIONS]

Add a note.

Options:
  --usage  Show this help and exit.
""",
        ),
        (
            ["tags", "--usage"],
            """\
Usage: notes tags [OPTIONS] COMMAND

Manage tags.

Options:
  --usage  Show this help and exit.

Commands:
  list     List tags.
""",
        ),
        (
            ["tags", "list", "--usage"],
            """\
Usage: notes tags list [OPTIONS]

List tags.

Options:
  --usage  Show this help and exit.
""",
        ),
    ],
)
def test_group_help_flags_apply_to_everything_inside(
    args: list[str], expected: str
) -> None:
    @group("notes", help_flags=["--usage"])
    def notes() -> None:
        """Keep notes."""

    @command("add")
    def add() -> None:
        """Add a note."""

    @group("tags")
    def tags() -> None:
        """Manage tags."""

    @command("list")
    def list_tags() -> None:
        """List tags."""

    notes.add(add, tags)
    tags.add(list_tags)

    result = run(notes, args)

    assert result.returncode == 0
    assert result.stdout == expected
    assert result.stderr == ""


@pytest.mark.parametrize(
    "args", [["--usage"], ["tags", "--usage"], ["tags", "list", "--usage"]]
)
def test_help_flags_true_inherits_at_every_depth(args: list[str]) -> None:
    @group("notes", help_flags=["--usage"])
    def notes() -> None:
        """Keep notes."""

    @group("tags", help_flags=True)
    def tags() -> None:
        """Manage tags."""

    @command("list", help_flags=True)
    def list_tags() -> None:
        """List tags."""

    notes.add(tags)
    tags.add(list_tags)

    result = run(notes, args)

    assert result.returncode == 0
    assert "\nOptions:\n  --usage  Show this help and exit.\n" in result.stdout
    assert result.stderr == ""


def test_inherited_help_flags_drop_the_default_flags() -> None:
    @group("notes", help_flags=["--usage"])
    def notes() -> None:
        """Keep notes."""

    @group("tags", help_flags=True)
    def tags() -> None:
        """Manage tags."""

    @command("list", help_flags=True)
    def list_tags() -> None:
        """List tags."""

    notes.add(tags)
    tags.add(list_tags)

    result = run(notes, ["tags", "list", "-h"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: unknown option '-h'.\nRun 'notes tags list --usage' for usage.\n"
    )


@pytest.mark.parametrize(
    ("args", "returncode", "stdout", "stderr"),
    [
        (
            ["add", "-H"],
            0,
            """\
Usage: notes add [OPTIONS]

Add a note.

Options:
  -H  Show this help and exit.
""",
            "",
        ),
        (
            ["add", "--usage"],
            2,
            "",
            "error: unknown option '--usage'.\nRun 'notes add -H' for usage.\n",
        ),
        (
            ["tags", "list", "--help"],
            0,
            """\
Usage: notes tags list [OPTIONS]

List tags.

Options:
  -h, --help  Show this help and exit.
""",
            "",
        ),
        (
            ["tags", "list", "--usage"],
            2,
            "",
            (
                "error: unknown option '--usage'.\n"
                "Run 'notes tags list --help' for usage.\n"
            ),
        ),
    ],
)
def test_node_help_flags_override_the_inherited_ones(
    args: list[str], returncode: int, stdout: str, stderr: str
) -> None:
    @group("notes", help_flags=["--usage"])
    def notes() -> None:
        """Keep notes."""

    @command("add", help_flags=["-H"])
    def add() -> None:
        """Add a note."""

    @group("tags", help_flags=["-h", "--help"])
    def tags() -> None:
        """Manage tags."""

    @command("list")
    def list_tags() -> None:
        """List tags."""

    notes.add(add, tags)
    tags.add(list_tags)

    result = run(notes, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        returncode,
        stdout,
        stderr,
    )


@pytest.mark.parametrize(
    ("args", "returncode", "stdout", "stderr"),
    [
        (
            ["tags", "add", "--help"],
            0,
            """\
Usage: notes tags add [OPTIONS]

Add a tag.

Options:
  --help  Show this help and exit.
""",
            "",
        ),
        (
            ["tags"],
            2,
            "",
            """\
Usage: notes tags [OPTIONS] COMMAND

Manage tags.

Options:
  --help  Show this help and exit.

Commands:
  add     Add a tag.
""",
        ),
        (["list", "--help"], 2, "", "error: unknown option '--help'.\n"),
    ],
)
def test_nested_group_turns_help_back_on(
    args: list[str], returncode: int, stdout: str, stderr: str
) -> None:
    @group("notes", help_flags=False)
    def notes() -> None:
        """Keep notes."""

    @group("tags", help_flags=["--help"])
    def tags() -> None:
        """Manage tags."""

    @command("add")
    def add() -> None:
        """Add a tag."""

    @command("list")
    def list_notes() -> None:
        """List notes."""

    notes.add(tags, list_notes)
    tags.add(add)

    result = run(notes, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        returncode,
        stdout,
        stderr,
    )


def test_command_turns_off_inherited_help() -> None:
    @group("notes")
    def notes() -> None:
        """Keep notes."""

    @command("add", help_flags=False)
    def add() -> None:
        """Add a note."""

    notes.add(add)

    result = run(notes, ["add", "--help"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "error: unknown option '--help'.\n"


@ROOTS
@pytest.mark.parametrize("help_flags", ["--help", 1, None])
def test_help_flags_that_arent_a_bool_or_a_list_are_rejected(
    root: Root, kind: str, help_flags: object
) -> None:
    message = (
        f"@{kind} takes help_flags as True, False or a list of flags, "
        f'such as ["--help"], not {help_flags!r}.'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = root("notes", help_flags=help_flags)


@pytest.mark.parametrize("root", [command, group], ids=["command", "group"])
@pytest.mark.parametrize(
    "flag_",
    [
        "help",
        "-help",
        "-cc",
        "--Help",
        "--show_help",
        "-1",
        "---help",
        "-",
        "--",
        "--help-",
    ],
)
def test_help_flag_that_isnt_short_or_long_is_rejected(root: Root, flag_: str) -> None:
    message = f"{flag_!r} isn't a flag. {FLAG_RULE}"
    with pytest.raises(ValueError, match=exactly(message)):
        _ = root("notes", help_flags=["-h", flag_])


@ROOTS
@pytest.mark.parametrize("value", [1, None, b"-h"])
def test_help_flag_that_isnt_a_string_is_rejected(
    root: Root, kind: str, value: object
) -> None:
    message = (
        f"help_flags of @{kind} takes flags as strings, "
        f"such as '--help', not {value!r}."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = root("notes", help_flags=["--help", value])


@ROOTS
@pytest.mark.parametrize(
    ("help_flags", "repeated"),
    [(["--help", "-h", "--help"], "--help"), (["-h", "-h"], "-h")],
)
def test_help_flag_listed_twice_is_rejected(
    root: Root, kind: str, help_flags: list[str], repeated: str
) -> None:
    message = f"help_flags of @{kind} lists {repeated} twice. Remove one."
    with pytest.raises(ValueError, match=exactly(message)):
        _ = root("notes", help_flags=help_flags)


@ROOTS
@pytest.mark.parametrize("version", [1.4, 2, True, b"1.4.0"])
def test_version_that_isnt_a_string_is_rejected(
    root: Root, kind: str, version: object
) -> None:
    message = f'@{kind} takes version as a string, such as "1.4.0", not {version!r}.'
    with pytest.raises(TypeError, match=exactly(message)):
        _ = root("notes", version=version)


def test_version_is_opt_in() -> None:
    @command("notes")
    def notes() -> None:
        pass

    result = run(notes, ["--version"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: unknown option '--version'.\nRun 'notes --help' for usage.\n"
    )


@pytest.mark.parametrize(
    "args",
    [["--version"], ["tags", "--version"], ["tags", "add", "--version"]],
)
def test_version_flag_prints_the_program_and_the_version(args: list[str]) -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @group("tags")
    def tags() -> None:
        """Manage tags."""

    @command("add")
    @argument("name")
    def add(name: str) -> str:
        return name

    notes.add(tags)
    tags.add(add)

    result = run(notes, args)

    assert result.returncode == 0
    assert result.stdout == "notes 1.4.0\n"
    assert result.stderr == ""


def test_inherited_version_is_listed_before_help() -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @command("add")
    def add() -> None:
        """Add a note."""

    notes.add(add)

    expected = """\
Usage: notes add [OPTIONS]

Add a note.

Options:
  --version   Show the version and exit.
  -h, --help  Show this help and exit.
"""

    result = run(notes, ["add", "-h"])

    assert result.stdout == expected


def test_version_before_a_bare_nested_group_prints_the_version() -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @group("tags")
    def tags() -> None:
        """Manage tags."""

    @command("add")
    def add() -> None:
        """Add a tag."""

    notes.add(tags)
    tags.add(add)

    result = run(notes, ["--version", "tags"])

    assert result.returncode == 0
    assert result.stdout == "notes 1.4.0\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("args", "returncode", "stdout", "stderr"),
    [
        (["--version"], 0, "notes 1.4.0\n", ""),
        (
            ["-V"],
            2,
            "",
            "error: unknown option '-V'.\nRun 'notes --help' for usage.\n",
        ),
        (
            ["-h"],
            0,
            """\
Usage: notes [OPTIONS]

Keep notes.

Options:
  -q, --quiet  Print less.
  --version    Show the version and exit.
  -h, --help   Show this help and exit.
""",
            "",
        ),
    ],
)
def test_version_adds_only_the_version_flag(
    args: list[str], returncode: int, stdout: str, stderr: str
) -> None:
    @command("notes", version="1.4.0")
    @flag("quiet", "-q", help="Print less.")
    def notes(*, quiet: bool = False) -> None:
        """Keep notes."""
        _ = quiet

    result = run(notes, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        returncode,
        stdout,
        stderr,
    )


@pytest.mark.parametrize(
    ("args", "stdout"),
    [
        (["--version"], "notes 1.4.0\n"),
        (["add", "--version"], "notes 2.0.0\n"),
        (["tags", "--version"], "notes 3.0.0\n"),
        (["tags", "list", "--version"], "notes 3.0.0\n"),
    ],
)
def test_node_version_overrides_the_inherited_one(args: list[str], stdout: str) -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @command("add", version="2.0.0")
    def add() -> None:
        """Add a note."""

    @group("tags", version="3.0.0")
    def tags() -> None:
        """Manage tags."""

    @command("list")
    def list_tags() -> None:
        """List tags."""

    notes.add(add, tags)
    tags.add(list_tags)

    result = run(notes, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, stdout, "")


@pytest.mark.parametrize("args", [["--version=2"], ["--version="]])
def test_version_flag_with_a_value_is_an_error(args: list[str]) -> None:
    @command("notes", version="1.4.0")
    def notes() -> None:
        pass

    result = run(notes, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: --version doesn't take a value.\nRun 'notes --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("args", "stdout"),
    [
        (["--version", "--help"], VERSIONED_NOTES_HELP),
        (["--help", "--version"], "notes 1.4.0\n"),
        (["--version", "-h"], VERSIONED_NOTES_HELP),
        (["-h", "--version"], "notes 1.4.0\n"),
        (["-h", "add", "--version"], "notes 1.4.0\n"),
        (["--version", "add", "--help"], VERSIONED_ADD_HELP),
    ],
)
def test_last_help_or_version_flag_wins(args: list[str], stdout: str) -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @command("add")
    def add() -> None:
        """Add a note."""

    notes.add(add)

    result = run(notes, args)

    assert result.returncode == 0
    assert result.stdout == stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("args", "stdout"),
    [
        (["--", "--version"], "--version\n"),
        (["--", "-h", "--version"], "-h --version\n"),
    ],
)
def test_version_flag_after_double_dash_is_a_word(args: list[str], stdout: str) -> None:
    @command("echo", version="1.4.0")
    @argument("words")
    def echo(words: list[str]) -> str:
        return " ".join(words)

    result = run(echo, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, stdout, "")


def test_option_named_version_is_fine_without_a_version() -> None:
    @command("deploy")
    @option("version")
    def deploy(version: str = "latest") -> str:
        return version

    validate(deploy)
    result = run(deploy, ["--version", "2.0.0"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "2.0.0\n", "")


@CHECKS
def test_option_named_help_clashes_with_the_help_flag(check: Check) -> None:
    @option("help")
    def explain(help: str = "") -> str:
        return help

    cli = command("explain")(explain)
    message = '--help is used by both @option("help") and help.' + HELP_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(cli)
    line = explain.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "explain", line)]


@CHECKS
def test_option_using_h_clashes_with_the_help_flag(check: Check) -> None:
    @flag("human", "-h")
    def size(*, human: bool = False) -> bool:
        return human

    cli = command("size")(size)
    message = '-h is used by both @flag("human") and help.' + HELP_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(cli)
    line = size.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "size", line)]


@CHECKS
def test_group_option_using_h_clashes_with_the_help_flag(check: Check) -> None:
    @flag("human", "-h")
    def disk(*, human: bool = False) -> None:
        _ = human

    cli = group("disk")(disk)
    message = '-h is used by both @flag("human") and help.' + HELP_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(cli)
    line = disk.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("group", "disk", line)]


@CHECKS
def test_option_named_version_clashes_with_the_version_flag(check: Check) -> None:
    @option("version")
    def deploy(version: str = "latest") -> str:
        return version

    cli = command("deploy", version="1.4.0")(deploy)
    message = '--version is used by both @option("version") and version.' + VERSION_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(cli)
    line = deploy.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "deploy", line)]


@CHECKS
def test_help_flags_cant_include_the_version_flag(check: Check) -> None:
    def notes() -> None:
        pass

    cli = command("notes", help_flags=["-h", "--version"], version="1.4.0")(notes)
    message = "--version is used by both help_flags and version." + SHARED_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(cli)
    line = notes.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "notes", line)]


def test_help_flags_can_include_the_version_flag_without_a_version() -> None:
    @command("notes", help_flags=["--version"])
    def notes() -> None:
        """Keep notes."""

    validate(notes)
    result = run(notes, ["--version"])

    assert result.returncode == 0
    assert result.stdout.endswith("Options:\n  --version  Show this help and exit.\n")


@NESTED_CHECKS
def test_option_clashes_with_an_inherited_help_flag(check: Check) -> None:
    @group("notes", help_flags=["-H", "--help"])
    def notes() -> None:
        pass

    @group("tags")
    def tags() -> None:
        pass

    @option("host", "-H")
    def add(host: str = "") -> str:
        return host

    notes.add(tags)
    tags.add(command("add")(add))

    message = '-H is used by both @option("host") and help.' + HELP_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(notes)
    line = add.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "add", line)]


@NESTED_CHECKS
def test_option_clashes_with_an_inherited_version_flag(check: Check) -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        pass

    @group("tags")
    def tags() -> None:
        pass

    @flag("version")
    def add(*, version: bool = False) -> bool:
        return version

    notes.add(tags)
    tags.add(command("add")(add))

    message = '--version is used by both @flag("version") and version.' + VERSION_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(notes)
    line = add.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "add", line)]


@NESTED_CHECKS
def test_version_clashes_with_inherited_help_flags(check: Check) -> None:
    @group("notes", help_flags=["-h", "--version"])
    def notes() -> None:
        pass

    @group("tags")
    def tags() -> None:
        pass

    def add() -> None:
        pass

    notes.add(tags)
    tags.add(command("add", version="2.0.0")(add))

    message = "--version is used by both help_flags and version." + SHARED_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(notes)
    line = add.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "add", line)]


@NESTED_CHECKS
def test_help_flags_clash_with_an_inherited_version(check: Check) -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        pass

    @group("tags")
    def tags() -> None:
        pass

    def add() -> None:
        pass

    notes.add(tags)
    tags.add(command("add", help_flags=["--version"])(add))

    message = "--version is used by both help_flags and version." + SHARED_FIX
    with pytest.raises(ValueError, match=exactly(message)) as info:
        _ = check(notes)
    line = add.__code__.co_firstlineno
    assert info.value.__notes__ == [defined_at("command", "add", line)]


def test_clash_is_raised_only_by_a_run_that_reaches_the_node() -> None:
    @group("notes", version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @flag("version")
    def add(*, version: bool = False) -> bool:
        return version

    notes.add(command("add")(add))

    result = run(notes, ["--version"])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "notes 1.4.0\n",
        "",
    )
    message = '--version is used by both @flag("version") and version.' + VERSION_FIX
    with pytest.raises(ValueError, match=exactly(message)):
        _ = run(notes, ["add"])


def test_validate_accepts_a_cli_with_help_and_version() -> None:
    @group("notes", help_flags=["-H", "--usage"], version="1.4.0")
    @flag("verbose", "-v")
    def notes(*, verbose: bool = False) -> None:
        _ = verbose

    @command("add")
    @option("host", "-h")
    def add(host: str = "") -> str:
        return host

    notes.add(add)

    validate(notes)
    result = run(notes, ["add", "-h", "example.org"])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "example.org\n",
        "",
    )


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--bogus", "tags"], "unknown option '--bogus'."),
        (["-c", "x", "tags"], "-c/--count: 'x' isn't a whole number."),
    ],
)
def test_errors_before_a_bare_nested_group_win_over_its_help(
    args: list[str], error: str
) -> None:
    @group("notes")
    @option("count", "-c")
    def notes(count: int = 1) -> None:
        _ = count

    @group("tags")
    def tags() -> None: ...

    notes.add(tags)

    result = run(notes, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        (
            f"error: {error}\n"
            "error: 'notes tags' needs a command.\n"
            "Run 'notes tags --help' for usage.\n"
        ),
    )


def test_help_survives_a_width_of_one_column(monkeypatch: pytest.MonkeyPatch) -> None:
    @command("count")
    @option("count", "-c", help="How many notes to show.")
    def count_(count: int = 10) -> str:
        return str(count)

    monkeypatch.setenv("COLUMNS", "1")
    result = run(count_, ["-h"])

    assert result.returncode == 0
    assert result.stdout.startswith("Usage:\n       count\n       [OPTIONS]\n")


def test_string_defaults_that_would_look_blank_are_quoted() -> None:
    @command("ws")
    @option("sep", help="Separator.")
    @option("end")
    @option("prompt")
    def ws(sep: str = " ", end: str = "\n", prompt: str = "> ") -> str:
        return sep + end + prompt

    result = run(ws, ["-h"])

    assert result.stdout == (
        "Usage: ws [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  --sep TEXT     Separator. (default: ' ')\n"
        "  --end TEXT     (default: '\\n')\n"
        "  --prompt TEXT  (default: '> ')\n"
        "  -h, --help     Show this help and exit.\n"
    )


def test_help_text_whitespace_is_collapsed() -> None:
    @command("count")
    @option(
        "count",
        "-c",
        help="""
        How many notes to show,
        counting from the newest one.
        """,
    )
    def count_(count: int = 10) -> str:
        return str(count)

    result = run(count_, ["-h"])

    assert result.stdout == (
        "Usage: count [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  -c, --count INT  How many notes to show, counting from the newest one.\n"
        "                   (default: 10)\n"
        "  -h, --help       Show this help and exit.\n"
    )


def test_summary_ends_at_a_line_of_only_spaces() -> None:
    def ws() -> None:
        pass

    ws.__doc__ = "\n    Show odd defaults.\n        \n    Not in the summary.\n    "
    cli = command("ws")(ws)

    result = run(cli, ["-h"])

    assert result.stdout == (
        "Usage: ws [OPTIONS]\n"
        "\n"
        "Show odd defaults.\n"
        "\n"
        "Options:\n"
        "  -h, --help  Show this help and exit.\n"
    )


@pytest.mark.parametrize(
    ("decorator", "name"),
    [
        (argument, "argument"),
        (option, "option"),
        (flag, "flag"),
        (env, "env"),
        (stdin, "stdin"),
    ],
)
def test_help_that_isnt_a_string_is_rejected(
    decorator: Callable[..., object], name: str
) -> None:
    message = f'@{name} takes help as a string, such as help="How many.", not 3.'
    with pytest.raises(TypeError, match=re.escape(message)):
        _ = decorator("count", help=3)


class Writer:
    def __init__(self, fd: int | None = None) -> None:
        self.text: str = ""
        self.fd: int | None = fd

    def write(self, text: str) -> int:
        self.text += text
        return len(text)

    def flush(self) -> None:
        pass

    def __getattr__(self, name: str) -> object:
        if name == "fileno" and self.fd is not None:
            return lambda: self.fd
        raise AttributeError(name)


def forty_columns_on_stderr(fd: int) -> os.terminal_size:
    if fd == 2:
        return os.terminal_size((40, 24))
    raise OSError


NARROW_NOTES_HELP = """\
Usage: notes [OPTIONS] COMMAND

Keep notes in a local database.

Options:
  -t, --text TEXT
                  Only show notes
                  whose title or body
                  has the text.
                  (default: '')
  -h, --help      Show this help and
                  exit.

Commands:
  add             Add a note.
"""

WIDE_NOTES_HELP = """\
Usage: notes [OPTIONS] COMMAND

Keep notes in a local database.

Options:
  -t, --text TEXT  Only show notes whose title or body has the text. (default:
                   '')
  -h, --help       Show this help and exit.

Commands:
  add              Add a note.
"""


def notes_with_text() -> Callable[[], object]:
    @group("notes")
    @option("text", "-t", help="Only show notes whose title or body has the text.")
    def notes(text: str = "") -> None:
        """Keep notes in a local database."""
        _ = text

    @command("add")
    def add() -> None:
        """Add a note."""

    notes.add(add)
    return notes


@pytest.mark.parametrize("columns", [None, "0", "wide"])
def test_help_measures_the_stream_it_writes_to(
    monkeypatch: pytest.MonkeyPatch, columns: str | None
) -> None:
    if columns is not None:
        monkeypatch.setenv("COLUMNS", columns)
    monkeypatch.setattr(os, "get_terminal_size", forty_columns_on_stderr)
    notes = notes_with_text()
    stderr = Writer(2)
    stdout = Writer()
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "stdout", stdout)
    for argv, code in ((["notes"], 2), (["notes", "--help"], 0)):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exit_info:
            _ = notes()
        assert exit_info.value.code == code
    assert stderr.text == NARROW_NOTES_HELP
    assert stdout.text == WIDE_NOTES_HELP


def test_flag_before_a_command_uses_the_options_where_it_was_written() -> None:
    @group("notes", help_flags=["--usage"], version="1.4.0")
    def notes() -> None:
        """Keep notes."""

    @command("add", help_flags=["-H"], version="2.0.0")
    def add() -> None:
        """Add a note."""

    notes.add(add)

    version = run(notes, ["--version", "add"])
    usage = run(notes, ["--usage", "add"])

    assert (version.returncode, version.stdout) == (0, "notes 1.4.0\n")
    assert (usage.returncode, usage.stdout) == (
        0,
        (
            "Usage: notes [OPTIONS] COMMAND\n"
            "\n"
            "Keep notes.\n"
            "\n"
            "Options:\n"
            "  --version  Show the version and exit.\n"
            "  --usage    Show this help and exit.\n"
            "\n"
            "Commands:\n"
            "  add        Add a note.\n"
        ),
    )


def test_defaults_keep_their_whitespace_and_enum_lists_their_tokens() -> None:
    @command("ws")
    @option("a")
    @option("c")
    @option("tab")
    @option("levels")
    def ws(
        a: str = "  ",
        c: str = "x  y",
        tab: str = "a\tb",
        levels: tuple[Priority, ...] = (Priority.VERY_HIGH, Priority.LOW),
    ) -> str:
        return f"{a}{c}{tab}{levels}"

    result = run(ws, ["-h"])

    assert result.stdout == (
        "Usage: ws [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  --a TEXT              (default: '  ')\n"
        "  --c TEXT              (default: x  y)\n"
        "  --tab TEXT            (default: 'a\\tb')\n"
        "  --levels [low|normal|very-high]\n"
        "                        Repeatable. (default: very-high, low)\n"
        "  -h, --help            Show this help and exit.\n"
    )


def test_wrapping_keeps_non_breaking_spaces_and_hyphenated_words() -> None:
    size_help = (
        "Keep at most this many blocks of storage for every note, at 10\xa0MB each."
    )

    @option("size", help=size_help)
    def find(size: int = 1) -> str:
        return str(size)

    find.__doc__ = (
        "Only show notes whose title or body has the text, "
        "and match the case-insensitively."
    )

    result = run(command("find")(find), ["-h"])

    assert result.stdout == (
        "Usage: find [OPTIONS]\n"
        "\n"
        "Only show notes whose title or body has the text, and match the\n"
        "case-insensitively.\n"
        "\n"
        "Options:\n"
        "  --size INT  Keep at most this many blocks of storage for every note, at\n"
        "              10\xa0MB each. (default: 1)\n"
        "  -h, --help  Show this help and exit.\n"
    )


def test_summary_skips_leading_lines_of_only_spaces() -> None:
    def lead() -> None:
        pass

    lead.__doc__ = "\n        \n    Add a note.\n\n    More.\n    "

    result = run(command("lead")(lead), ["-h"])

    assert result.stdout == (
        "Usage: lead [OPTIONS]\n"
        "\n"
        "Add a note.\n"
        "\n"
        "Options:\n"
        "  -h, --help  Show this help and exit.\n"
    )


FIND_SUMMARY = (
    "Find notes whose title, body or tags match the given text, newest ones first"
)


@pytest.mark.parametrize(
    ("summary", "shown"),
    [
        (f"{FIND_SUMMARY}!!", f"{FIND_SUMMARY}!!"),
        (f"{FIND_SUMMARY}!!!", FIND_SUMMARY.replace(" first", "\nfirst") + "!!!"),
    ],
    ids=["78", "79"],
)
def test_help_wraps_at_exactly_78_columns(summary: str, shown: str) -> None:
    def find() -> None:
        pass

    find.__doc__ = summary

    result = run(command("find")(find), ["-h"])

    assert len(summary) in {78, 79}
    assert result.stdout.split("\n\n")[1] == shown


DEFAULT_DB = Path("notes.db")


@group("notes")
@env("notes_db", help="Where notes are stored.")
@flag("quiet", "-q", help="Print nothing but results.")
def stored_notes(notes_db: Path = DEFAULT_DB, *, quiet: bool = False) -> None:
    """Keep notes in a local database."""
    _ = (notes_db, quiet)


@command("add")
@argument("text", help="The note.")
@option("tag", "-t", help="A tag to file it under.")
@env("editor", variable="VISUAL", help="Editor for long notes.")
@env("max_length", help="Longest note to accept.")
@env("level", help="How loud.")
def add_stored_note(
    text: str,
    editor: str,
    tag: str | None = None,
    max_length: int = 280,
    level: Literal["low", "high"] = "low",
) -> None:
    """Add a note."""
    _ = (text, editor, tag, max_length, level)


stored_notes.add(add_stored_note)


def test_group_help_lists_its_variables_before_its_commands() -> None:
    result = run(stored_notes, ["--help"])

    assert result.stdout == (
        "Usage: notes [OPTIONS] COMMAND\n"
        "\n"
        "Keep notes in a local database.\n"
        "\n"
        "Options:\n"
        "  -q, --quiet  Print nothing but results.\n"
        "  -h, --help   Show this help and exit.\n"
        "\n"
        "Environment:\n"
        "  NOTES_DB     Where notes are stored. (default: notes.db)\n"
        "\n"
        "Commands:\n"
        "  add          Add a note.\n"
    )


def test_command_help_lists_the_variables_of_every_node_on_its_path() -> None:
    result = run(stored_notes, ["add", "--help"])

    assert result.stdout == (
        "Usage: notes [OPTIONS] add [OPTIONS] TEXT\n"
        "\n"
        "Add a note.\n"
        "\n"
        "Arguments:\n"
        "  TEXT              The note.\n"
        "\n"
        "Options:\n"
        "  -t, --tag TEXT    A tag to file it under.\n"
        "  -h, --help        Show this help and exit.\n"
        "\n"
        "Options for notes:\n"
        "  -q, --quiet       Print nothing but results.\n"
        "\n"
        "Environment:\n"
        "  NOTES_DB          Where notes are stored. (default: notes.db)\n"
        "  VISUAL            Editor for long notes. (required)\n"
        "  MAX_LENGTH        Longest note to accept. (default: 280)\n"
        "  LEVEL [low|high]  How loud. (default: low)\n"
    )


def test_long_variable_moves_its_help_to_the_next_line() -> None:
    @command("sync")
    @env("token", variable="NOTES_SYNC_SERVICE_ACCESS_TOKEN", help="The token.")
    def sync(token: str) -> None:
        _ = token

    result = run(sync, ["--help"])

    assert result.stdout == (
        "Usage: sync [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  -h, --help            Show this help and exit.\n"
        "\n"
        "Environment:\n"
        "  NOTES_SYNC_SERVICE_ACCESS_TOKEN\n"
        "                        The token. (required)\n"
    )


def test_group_with_only_variables_shows_no_options_before_its_command() -> None:
    @group("box")
    @env("box_db")
    def box(box_db: str = "") -> None:
        _ = box_db

    @command("put")
    def put() -> None:
        """Put something in the box."""

    box.add(put)

    result = run(box, ["put", "--help"])

    assert result.stdout == (
        "Usage: box put [OPTIONS]\n"
        "\n"
        "Put something in the box.\n"
        "\n"
        "Options:\n"
        "  -h, --help  Show this help and exit.\n"
        "\n"
        "Environment:\n"
        "  BOX_DB      (default: '')\n"
    )


def test_help_lists_piped_input_under_input() -> None:
    @command("total")
    @stdin("numbers", help="Numbers to add.")
    def total(numbers: list[int]) -> int:
        """Add up numbers, one per line."""
        return sum(numbers)

    result = run(total, ["--help"])

    assert result.stdout == (
        "Usage: total [OPTIONS]\n"
        "\n"
        "Add up numbers, one per line.\n"
        "\n"
        "Options:\n"
        "  -h, --help  Show this help and exit.\n"
        "\n"
        "Input:\n"
        "  stdin       Numbers to add. One per line. (required)\n"
    )


def test_input_comes_after_environment_and_shows_choices() -> None:
    @command("say")
    @env("voice", help="Who speaks.")
    @stdin("level", help="How loud.")
    def say(voice: str = "robot", level: Literal["low", "high"] = "low") -> None:
        _ = (voice, level)

    result = run(say, ["--help"])

    assert result.stdout == (
        "Usage: say [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  -h, --help        Show this help and exit.\n"
        "\n"
        "Environment:\n"
        "  VOICE             Who speaks. (default: robot)\n"
        "\n"
        "Input:\n"
        "  stdin [low|high]  How loud. (default: low)\n"
    )


def test_help_lists_dependencies() -> None:
    @command(
        "connect",
        dependencies=[
            dependency.exactly(1, "token", "user"),
            dependency.together("user", "password"),
        ],
    )
    @option("host", help="Server to connect to.")
    @option("token", help="An access token.")
    @option("user", "-u", help="User name.")
    @option("password", "-p", help="Password for --user.")
    def connect(
        host: str,
        token: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        """Connect to a server with a token, or a user name and password."""
        _ = (host, token, user, password)

    result = run(connect, ["--help"])

    assert result.stdout == (
        "Usage: connect [OPTIONS]\n"
        "\n"
        "Connect to a server with a token, or a user name and password.\n"
        "\n"
        "Options:\n"
        "  --host TEXT          Server to connect to. (required)\n"
        "  --token TEXT         An access token.\n"
        "  -u, --user TEXT      User name.\n"
        "  -p, --password TEXT  Password for --user.\n"
        "  -h, --help           Show this help and exit.\n"
        "\n"
        "Dependencies:\n"
        "  Exactly 1 of --token and -u/--user must be given.\n"
        "  -u/--user and -p/--password must be given together.\n"
    )


def test_help_describes_each_kind_of_dependency() -> None:
    @command(
        "pick",
        dependencies=[
            dependency.requires("a", "b", "c"),
            dependency.requires_any("a", "b", "c"),
            dependency.conflicts("a", "b", "c"),
            dependency.together("a", "b"),
            dependency.alone("d"),
            dependency.at_least(1, "a", "b"),
            dependency.at_most(2, "a", "b", "c"),
            dependency.exactly(1, "a", "b"),
        ],
    )
    @flag("a")
    @flag("b")
    @flag("c")
    @flag("d")
    def pick(
        *, a: bool = False, b: bool = False, c: bool = False, d: bool = False
    ) -> None:
        _ = (a, b, c, d)

    result = run(pick, ["--help"])

    assert result.stdout.split("\n\n")[-1] == (
        "Dependencies:\n"
        "  --a requires --b and --c.\n"
        "  --a requires --b or --c.\n"
        "  --a can't be used with --b or --c.\n"
        "  --a and --b must be given together.\n"
        "  --d must be given alone.\n"
        "  At least 1 of --a and --b must be given.\n"
        "  At most 2 of --a, --b and --c can be given.\n"
        "  Exactly 1 of --a and --b must be given.\n"
    )


def test_long_dependency_wraps_without_moving_the_help_column() -> None:
    @command(
        "sync",
        dependencies=[
            dependency.together(
                "first_long_input_name",
                "second_long_input_name",
                "third_long_input_name",
            )
        ],
    )
    @flag("first_long_input_name")
    @flag("second_long_input_name")
    @flag("third_long_input_name")
    def sync(
        *,
        first_long_input_name: bool = False,
        second_long_input_name: bool = False,
        third_long_input_name: bool = False,
    ) -> None:
        _ = (first_long_input_name, second_long_input_name, third_long_input_name)

    result = run(sync, ["--help"])

    assert result.stdout.split("\n\n")[-2:] == [
        (
            "Options:\n"
            "  --first-long-input-name\n"
            "  --second-long-input-name\n"
            "  --third-long-input-name\n"
            "  -h, --help            Show this help and exit."
        ),
        (
            "Dependencies:\n"
            "  --first-long-input-name, --second-long-input-name and\n"
            "    --third-long-input-name must be given together.\n"
        ),
    ]


def test_command_help_lists_its_groups_dependencies_after_its_own() -> None:
    @group("notes", dependencies=[dependency.conflicts("quiet", "verbose")])
    @flag("quiet", "-q")
    @flag("verbose", "-v")
    def notes(*, quiet: bool = False, verbose: bool = False) -> None:
        _ = (quiet, verbose)

    @command("list", dependencies=[dependency.requires("long", "archived")])
    @flag("long", "-l")
    @flag("archived", "-a")
    def list_notes(*, long: bool = False, archived: bool = False) -> None:
        _ = (long, archived)

    notes.add(list_notes)

    result = run(notes, ["list", "--help"])

    assert result.stdout.split("\n\n")[-2:] == [
        "Dependencies:\n  -l/--long requires -a/--archived.",
        "Dependencies for notes:\n  -q/--quiet can't be used with -v/--verbose.\n",
    ]


def test_dependencies_come_after_environment_and_input() -> None:
    @command("say", dependencies=[dependency.requires("loud", "voice")])
    @flag("loud")
    @env("voice", help="Who speaks.")
    @stdin("text", help="What to say.")
    def say(voice: str = "robot", text: str = "", *, loud: bool = False) -> None:
        _ = (voice, text, loud)

    result = run(say, ["--help"])

    assert [section.split(":")[0] for section in result.stdout.split("\n\n")] == [
        "Usage",
        "Options",
        "Environment",
        "Input",
        "Dependencies",
    ]


def test_help_shows_what_children_accept() -> None:
    @command("backup")
    @option("archive_format", "-f", help="Archive format.")
    @choices(("zip", "tar", "gztar", "bztar", "xztar"))
    @option("label", "-l", help="Added to the archive name.")
    @matches(r"[a-z0-9-]+")
    @length(high=20)
    @option("keep", "-k", help="How many archives to keep.")
    @between(1, 100)
    @option("workers", "-w", help="Parallel workers.")
    @between(low=1)
    def backup(
        archive_format: str = "gztar",
        label: str | None = None,
        keep: int = 10,
        workers: int = 4,
    ) -> None:
        """Archive the current directory."""
        _ = (archive_format, label, keep, workers)

    result = run(backup, ["--help"])

    assert result.stdout == (
        "Usage: backup [OPTIONS]\n"
        "\n"
        "Archive the current directory.\n"
        "\n"
        "Options:\n"
        "  -f, --archive-format [zip|tar|gztar|bztar|xztar]\n"
        "                        Archive format. (default: gztar)\n"
        "  -l, --label TEXT      Added to the archive name. Must match [a-z0-9-]+. At\n"
        "                        most 20 characters.\n"
        "  -k, --keep INT        How many archives to keep. 1 to 100. (default: 10)\n"
        "  -w, --workers INT     Parallel workers. At least 1. (default: 4)\n"
        "  -h, --help            Show this help and exit.\n"
    )


def test_help_sentences_for_each_kind_of_bound() -> None:
    @command("pick")
    @option("percent")
    @between(high=100)
    @option("since")
    @between(date(2020, 1, 1), date(2030, 12, 31))
    @option("user")
    @length(3, 20)
    @option("phrase")
    @length(low=12)
    @option("nickname")
    @length(low=1)
    def pick(
        percent: int = 50,
        since: date | None = None,
        user: str = "ada",
        phrase: str | None = None,
        nickname: str = "a",
    ) -> None:
        _ = (percent, since, user, phrase, nickname)

    lines = run(pick, ["--help"]).stdout.splitlines()

    assert [line.split(maxsplit=2)[2] for line in lines[3:8]] == [
        "At most 100. (default: 50)",
        "2020-01-01 to 2030-12-31.",
        "3 to 20 characters. (default: ada)",
        "At least 12 characters.",
        "At least 1 character. (default: a)",
    ]


def test_choices_replace_the_placeholder_of_every_kind_of_input() -> None:
    @command("pack")
    @argument("archive_format")
    @choices({"zip", "tar"})
    @env("level")
    @choices(1, 2, 3)
    @stdin("names")
    @choices("ada", "bob")
    def pack(archive_format: str, level: int = 1, names: tuple[str, ...] = ()) -> None:
        """Pack files."""
        _ = (archive_format, level, names)

    result = run(pack, ["--help"])

    assert "  ARCHIVE_FORMAT [tar|zip]\n" in result.stdout
    assert "  LEVEL [1|2|3]" in result.stdout
    assert "  stdin [ada|bob]" in result.stdout
    assert "One per line." in result.stdout
