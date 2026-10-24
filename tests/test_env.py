import os
import re
import sys
from collections.abc import Callable
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Literal

import pytest

from cliron import argument, command, env, group, option
from cliron.testing import run, validate

Check = Callable[..., object]

CHECKS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)

DEFAULT_DB = Path("notes.db")


class Level(Enum):
    LOW = "low"
    VERY_HIGH = "very high"


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@command("show")
@env("notes_db")
@env("user", variable="GITHUB_USER")
@env("from_")
def show(notes_db: Path, user: str = "nobody", from_: int = 0) -> str:
    return f"{notes_db} {user} {from_}"


@command("convert")
@env("count")
@env("path")
@env("level")
@env("mode")
@env("limit")
def convert(
    count: int,
    path: Path,
    level: Level,
    mode: Literal["fast", "slow"],
    limit: float | None = None,
) -> str:
    return f"{count!r} {path!r} {level!r} {mode!r} {limit!r}"


def test_env_reads_the_variable_named_after_the_parameter() -> None:
    result = run(show, [], env={"NOTES_DB": "a.db", "FROM": "3"})

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "a.db nobody 3\n",
        "",
    )


def test_env_reads_the_variable_it_names() -> None:
    result = run(show, [], env={"NOTES_DB": "a.db", "GITHUB_USER": "ada"})

    assert result.stdout == "a.db ada 0\n"


def test_env_converts_the_value_to_the_annotation() -> None:
    environment = {
        "COUNT": "3",
        "PATH": "notes.db",
        "LEVEL": "very-high",
        "MODE": "slow",
        "LIMIT": "2.5",
    }

    result = run(convert, [], env=environment)

    assert result.stdout == (
        f"3 {Path('notes.db')!r} <Level.VERY_HIGH: 'very high'> 'slow' 2.5\n"
    )


@pytest.mark.parametrize("environment", [{}, {"GITHUB_USER": "", "FROM": ""}])
def test_unset_or_empty_variable_takes_the_default(
    environment: dict[str, str],
) -> None:
    result = run(show, [], env={"NOTES_DB": "a.db", **environment})

    assert result.stdout == "a.db nobody 0\n"


@pytest.mark.parametrize("environment", [{}, {"NOTES_DB": ""}])
def test_unset_or_empty_required_variable_is_reported(
    environment: dict[str, str],
) -> None:
    result = run(show, [], env=environment)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: $NOTES_DB isn't set.\nRun 'show --help' for usage.\n",
    )


def test_invalid_value_is_reported_with_the_variable_before_misplaced_words() -> None:
    result = run(show, ["--nope"], env={"NOTES_DB": "a.db", "FROM": "x"})

    assert result.stderr == (
        "error: $FROM: 'x' isn't a whole number.\n"
        "error: unknown option '--nope'.\n"
        "Run 'show --help' for usage.\n"
    )


def test_every_error_is_reported_together() -> None:
    @group("notes")
    @env("notes_db")
    def notes(notes_db: Path = DEFAULT_DB) -> None:
        _ = notes_db

    @command("add")
    @argument("text")
    @option("tag", "-t")
    @env("editor", variable="VISUAL")
    @env("max_length")
    @env("level")
    def add(
        text: str,
        editor: str,
        tag: str | None = None,
        max_length: int = 280,
        level: Literal["low", "high"] = "low",
    ) -> None:
        _ = (text, editor, tag, max_length, level)

    notes.add(add)

    result = run(
        notes,
        ["add", "Buy milk", "--tagz", "x"],
        env={"NOTES_DB": "", "MAX_LENGTH": "abc", "LEVEL": "loud"},
    )

    assert result.returncode == 2
    assert result.stderr == (
        "error: $VISUAL isn't set.\n"
        "error: $MAX_LENGTH: 'abc' isn't a whole number.\n"
        "error: $LEVEL: 'loud' isn't one of low, high.\n"
        "error: unknown option '--tagz'. Did you mean '--tag'?\n"
        "Run 'notes add --help' for usage.\n"
    )


def test_group_passes_its_own_variable_to_its_function() -> None:
    seen: list[Path] = []

    @group("notes")
    @env("notes_db")
    def notes(notes_db: Path = DEFAULT_DB) -> None:
        seen.append(notes_db)

    @command("list")
    def list_notes() -> str:
        return "listed"

    notes.add(list_notes)

    result = run(notes, ["list"], env={"NOTES_DB": "other.db"})

    assert (result.stdout, seen) == ("listed\n", [Path("other.db")])


def test_group_run_alone_reports_an_invalid_variable_instead_of_its_usage() -> None:
    @group("notes")
    @env("page_size")
    def notes(page_size: int = 20) -> None:
        _ = page_size

    @command("list")
    def list_notes() -> None: ...

    notes.add(list_notes)

    result = run(notes, [], env={"PAGE_SIZE": "abc"})

    assert (result.returncode, result.stdout) == (2, "")
    assert result.stderr == (
        "error: $PAGE_SIZE: 'abc' isn't a whole number.\n"
        "error: 'notes' needs a command.\n"
        "Run 'notes --help' for usage.\n"
    )


def test_help_wins_over_a_missing_variable() -> None:
    result = run(show, ["--help"], env={})

    assert (result.returncode, result.stderr) == (0, "")


@CHECKS
def test_env_rejects_a_list(check: Check) -> None:
    @env("paths")
    def tidy(paths: list[Path]) -> None:
        _ = paths

    message = (
        f"parameter 'paths' has the type {list[Path]!r}, but @env(\"paths\") "
        "reads one value. Use a type without list or tuple."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(command("tidy")(tidy))


@CHECKS
@pytest.mark.parametrize(
    ("variable", "example"), [(None, "DEBUG"), ("APP_DEBUG", "APP_DEBUG")]
)
def test_env_rejects_a_bool_and_suggests_an_int(
    check: Check, variable: str | None, example: str
) -> None:
    @env("debug", variable=variable)
    def tidy(*, debug: bool = False) -> None:
        _ = debug

    message = (
        "parameter 'debug' is a bool, which only @flag can fill. For an "
        f"environment variable, use an int, such as debug: int = 0, which {example}=1 "
        "sets to 1."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(command("tidy")(tidy))


@pytest.mark.parametrize("decorator", [env])
def test_env_rejects_a_variable_that_isnt_a_string(
    decorator: Callable[..., object],
) -> None:
    message = '@env takes variable as a string, such as variable="GITHUB_TOKEN", not 1.'
    with pytest.raises(TypeError, match=exactly(message)):
        _ = decorator("token", variable=1)


@pytest.mark.parametrize("variable", ["", "MY-TOKEN", "1TOKEN", "TOKEN "])
def test_env_rejects_an_invalid_variable_name(variable: str) -> None:
    message = (
        f"{variable!r} isn't an environment variable name. Use letters, digits "
        "and underscores, not starting with a digit, such as 'GITHUB_TOKEN'."
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = env("token", variable=variable)


def test_env_accepts_a_lowercase_variable_name() -> None:
    @command("fetch")
    @env("proxy", variable="http_proxy")
    def fetch(proxy: str) -> str:
        return proxy

    assert run(fetch, [], env={"http_proxy": "localhost:3128"}).stdout == (
        "localhost:3128\n"
    )


def test_two_parents_cant_read_one_variable() -> None:
    @env("first", variable="TOKEN")
    @env("second", variable="TOKEN")
    def login(first: str, second: str) -> None:
        _ = (first, second)

    message = '$TOKEN is used by both @env("first") and @env("second").'
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("login")(login)


def test_variable_may_share_its_name_with_an_argument_placeholder() -> None:
    @command("copy")
    @argument("db")
    @env("path", variable="DB")
    def copy(db: str, path: str) -> str:
        return f"{db} {path}"

    assert run(copy, ["x"], env={"DB": "y"}).stdout == "x y\n"


def test_run_replaces_the_environment_and_restores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTES_DB", "outer.db")

    @command("peek")
    def peek() -> str:
        return ",".join(sorted(os.environ))

    assert run(peek, [], env={"ONLY": "1"}).stdout == "ONLY\n"
    assert os.environ["NOTES_DB"] == "outer.db"
    assert "ONLY" not in os.environ


def test_run_restores_the_environment_when_an_exception_propagates() -> None:
    before = dict(os.environ)

    @command("boom")
    def boom() -> None:
        raise RuntimeError

    with pytest.raises(RuntimeError):
        _ = run(boom, [], env={})

    assert dict(os.environ) == before


def test_run_without_env_keeps_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTES_DB", "outer.db")
    monkeypatch.delenv("GITHUB_USER", raising=False)
    monkeypatch.delenv("FROM", raising=False)

    assert run(show, []).stdout == "outer.db nobody 0\n"


def test_calling_the_cli_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOTES_DB", "outer.db")
    monkeypatch.delenv("GITHUB_USER", raising=False)
    monkeypatch.delenv("FROM", raising=False)
    monkeypatch.setattr(sys, "argv", ["show.py"])

    with pytest.raises(SystemExit) as info:
        show()

    assert info.value.code == 0
    assert capsys.readouterr() == ("outer.db nobody 0\n", "")
