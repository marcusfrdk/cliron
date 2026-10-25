import io
import os
import re
import sys
from collections.abc import Callable
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Literal, TextIO

import pytest

from cliron import command, group, option, stdin
from cliron.testing import run, validate

Check = Callable[..., object]

CHECKS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX terminal")


class Level(Enum):
    LOW = "low"
    VERY_HIGH = "very high"


class Unreadable:
    def read(self) -> str:
        message = "stdin was read"
        raise AssertionError(message)


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@command("echo")
@stdin("text")
def echo(text: str) -> str:
    return repr(text)


@command("greet")
@stdin("name")
def greet(name: str = "nobody") -> str:
    return f"Hello, {name}!"


@command("total")
@stdin("numbers")
def total(numbers: list[int]) -> int:
    return sum(numbers)


@command("lines")
@stdin("lines")
def lines(lines: tuple[str, ...]) -> list[str]:
    return list(lines)


@command("double")
@stdin("number")
def double(number: int) -> int:
    return number * 2


@command("where")
@stdin("path")
def where(path: Path) -> str:
    return repr(path)


@command("loud")
@stdin("level")
def loud(level: Level) -> str:
    return level.name


@command("pace")
@stdin("mode")
def pace(mode: Literal["fast", "slow"]) -> str:
    return mode


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Ada\n", "Ada"),
        ("Ada\r\n", "Ada"),
        ("Ada", "Ada"),
        ("Ada\n\n", "Ada\n"),
        ("two\nlines\n", "two\nlines"),
        ("Ada\r", "Ada\r"),
        ("", ""),
    ],
)
def test_text_loses_one_final_line_break(text: str, value: str) -> None:
    result = run(echo, [], input=text)

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        f"{value!r}\n",
        "",
    )


CONVERTERS = {"int": double, "path": where, "enum": loud, "literal": pace}


@pytest.mark.parametrize(
    ("kind", "text", "output"),
    [
        ("int", "21\n", "42\n"),
        ("path", "notes.db\n", f"{Path('notes.db')!r}\n"),
        ("enum", "very-high\n", "VERY_HIGH\n"),
        ("literal", "slow\n", "slow\n"),
    ],
)
def test_text_is_converted_to_the_annotation(kind: str, text: str, output: str) -> None:
    assert run(CONVERTERS[kind], [], input=text).stdout == output


@pytest.mark.parametrize("text", ["1\n2\n3\n", "1\r\n2\r\n3\r\n", "1\n2\n3"])
def test_list_gets_one_item_per_line(text: str) -> None:
    assert run(total, [], input=text).stdout == "6\n"


def test_empty_line_in_the_middle_is_an_item() -> None:
    result = run(lines, [], input="a\n\nb\n")

    assert result.stdout == '[\n  "a",\n  "",\n  "b"\n]\n'


@pytest.mark.parametrize("text", ["", "\n"])
def test_empty_input_gives_a_list_no_items(text: str) -> None:
    assert run(total, [], input=text).stdout == "0\n"


def test_empty_input_counts_as_given() -> None:
    result = run(double, [], input="")

    assert (result.returncode, result.stderr) == (
        2,
        "error: stdin: '' isn't a whole number.\nRun 'double --help' for usage.\n",
    )


def test_nothing_piped_takes_the_default() -> None:
    assert run(greet, []).stdout == "Hello, nobody!\n"


def test_nothing_piped_names_the_command_path_in_its_error() -> None:
    @group("notes")
    def notes() -> None: ...

    @command("import")
    @stdin("text")
    def import_notes(text: str) -> None:
        _ = text

    notes.add(import_notes)

    result = run(notes, ["import"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        (
            "error: stdin: nothing was piped in. For example: cat file.txt | "
            "notes import\nRun 'notes import --help' for usage.\n"
        ),
    )


def test_each_bad_line_is_reported_with_its_number() -> None:
    result = run(total, [], input="1\ntwo\n3\nfour\n")

    assert result.stderr == (
        "error: stdin: line 2: 'two' isn't a whole number.\n"
        "error: stdin: line 4: 'four' isn't a whole number.\n"
        "Run 'total --help' for usage.\n"
    )


def test_stdin_errors_keep_declaration_order() -> None:
    @command("add")
    @option("count")
    @stdin("numbers")
    def add(numbers: list[int], count: int = 1) -> int:
        return sum(numbers) * count

    result = run(add, ["--count", "x", "--nope"], input="1\ntwo\n")

    assert result.stderr == (
        "error: --count: 'x' isn't a whole number.\n"
        "error: stdin: line 2: 'two' isn't a whole number.\n"
        "error: unknown option '--nope'.\n"
        "Run 'add --help' for usage.\n"
    )


def test_help_doesnt_read_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", Unreadable())
    monkeypatch.setattr(sys, "argv", ["echo.py", "--help"])

    with pytest.raises(SystemExit) as info:
        echo()

    assert info.value.code == 0
    assert capsys.readouterr().out.startswith("Usage: echo [OPTIONS]\n")


def test_group_cant_read_stdin() -> None:
    @stdin("text")
    def notes(text: str) -> None:
        _ = text

    message = "group 'notes' can't read stdin. Use @stdin(\"text\") on a command."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = group("notes")(notes)


def test_command_reads_stdin_once() -> None:
    @stdin("text")
    @stdin("lines")
    def cat(text: str, lines: list[str]) -> None:
        _ = (text, lines)

    message = 'stdin is used by both @stdin("text") and @stdin("lines").'
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("cat")(cat)


def test_an_option_and_stdin_with_the_same_name_are_rejected() -> None:
    @option("text")
    @stdin("text")
    def show(text: str = "") -> str:
        return text

    message = 'parameter \'text\' has two parents, @option("text") and @stdin("text").'
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("show")(show)


@CHECKS
def test_stdin_rejects_a_bool(check: Check) -> None:
    @stdin("verbose")
    def show(*, verbose: bool = False) -> bool:
        return verbose

    message = "parameter 'verbose' is a bool. Use @flag(\"verbose\")."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(command("show")(show))


@pytest.mark.parametrize("text", [None, "Ada"])
def test_run_restores_stdin_and_closes_its_stream(text: str | None) -> None:
    before = sys.stdin
    seen: list[TextIO] = []

    @command("peek")
    def peek() -> None:
        seen.append(sys.stdin)

    _ = run(peek, [], input=text)

    assert sys.stdin is before
    assert [stream.closed for stream in seen] == [True]


def test_run_restores_stdin_when_an_exception_propagates() -> None:
    before = sys.stdin

    @command("boom")
    def boom() -> None:
        raise RuntimeError

    with pytest.raises(RuntimeError):
        _ = run(boom, [], input="Ada")

    assert sys.stdin is before


def call(
    cli: Callable[[], object],
    stream: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[object, str, str]:
    monkeypatch.setattr(sys, "stdin", stream)
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    with pytest.raises(SystemExit) as info:
        _ = cli()
    output = capsys.readouterr()
    return info.value.code, output.out, output.err


def test_missing_stdin_means_nothing_piped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert call(greet, None, monkeypatch, capsys) == (0, "Hello, nobody!\n", "")


@POSIX
def test_a_terminal_is_never_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    controller, terminal = os.openpty()
    try:
        with os.fdopen(terminal) as stream:
            result = call(greet, stream, monkeypatch, capsys)
    finally:
        os.close(controller)

    assert result == (0, "Hello, nobody!\n", "")


def test_an_empty_pipe_counts_as_given(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    read_end, write_end = os.pipe()
    os.close(write_end)
    with os.fdopen(read_end) as stream:
        result = call(greet, stream, monkeypatch, capsys)

    assert result == (0, "Hello, !\n", "")


def test_undecodable_input_is_an_input_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = io.BytesIO(b"bad \xff byte\n")
    with io.TextIOWrapper(raw, encoding="utf-8", errors="strict") as stream:
        result = call(echo, stream, monkeypatch, capsys)

    assert result == (
        2,
        "",
        (
            "error: stdin: the input isn't valid utf-8 text.\n"
            "Run 'echo --help' for usage.\n"
        ),
    )
