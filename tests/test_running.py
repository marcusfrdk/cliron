import math
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import cast

import pytest

from cliron import argument, command, flag, group
from cliron.testing import run

PERSON_JSON = """\
{
  "name": "Ada",
  "tags": [
    "math",
    "engines"
  ]
}
"""

NUMBERS_JSON = """\
[
  1,
  2.5
]
"""

ACCENT_JSON = """\
{
  "city": "Malmö",
  "word": "é"
}
"""

UNREPRESENTABLE_NOTE = (
    "command 'show-data' returned it. "
    "Return None, a str, or data that JSON can represent."
)


def test_none_return_value_prints_nothing() -> None:
    calls: list[str] = []

    @command("greet")
    def greet() -> None:
        calls.append("greet")

    result = run(greet, [])

    assert calls == ["greet"]
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("value", "stdout"),
    [
        pytest.param("Hello, Ada!", "Hello, Ada!\n", id="text"),
        pytest.param("", "\n", id="empty"),
        pytest.param("one\ntwo", "one\ntwo\n", id="lines"),
        pytest.param("Malmö", "Malmö\n", id="non-ascii"),
    ],
)
def test_str_return_value_is_printed_with_a_newline(value: str, stdout: str) -> None:
    @command("greet")
    def greet() -> str:
        return value

    result = run(greet, [])

    assert result.returncode == 0
    assert result.stdout == stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("value", "stdout"),
    [
        pytest.param(
            {"name": "Ada", "tags": ["math", "engines"]}, PERSON_JSON, id="dict"
        ),
        pytest.param([1, 2.5], NUMBERS_JSON, id="list"),
        pytest.param({}, "{}\n", id="empty-dict"),
        pytest.param([], "[]\n", id="empty-list"),
        pytest.param(3, "3\n", id="int"),
        pytest.param(0, "0\n", id="zero"),
        pytest.param(True, "true\n", id="true"),
        pytest.param(False, "false\n", id="false"),
        pytest.param(1.5, "1.5\n", id="float"),
        pytest.param({"city": "Malmö", "word": "é"}, ACCENT_JSON, id="non-ascii"),
    ],
)
def test_other_return_values_are_printed_as_indented_json(
    value: object, stdout: str
) -> None:
    @command("show")
    def show() -> object:
        return value

    result = run(show, [])

    assert result.returncode == 0
    assert result.stdout == stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(Path("notes.txt"), id="path"),
        pytest.param({"a", "b"}, id="set"),
    ],
)
def test_unserializable_return_value_raises_type_error_naming_the_command(
    value: object,
) -> None:
    @command("show_data")
    def show_data() -> object:
        return value

    with pytest.raises(TypeError) as info:
        _ = run(show_data, [])

    assert info.value.__notes__ == [UNREPRESENTABLE_NOTE]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(math.nan, id="nan"),
        pytest.param(math.inf, id="inf"),
        pytest.param(-math.inf, id="negative-inf"),
    ],
)
def test_out_of_range_float_raises_value_error_naming_the_command(
    value: float,
) -> None:
    @command("show_data")
    def show_data() -> float:
        return value

    with pytest.raises(ValueError, match="not JSON compliant") as info:
        _ = run(show_data, [])

    assert info.value.__notes__ == [UNREPRESENTABLE_NOTE]


def test_uncaught_exception_propagates_out_of_run() -> None:
    @command("fail")
    def fail() -> None:
        message = "disk full"
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="disk full"):
        _ = run(fail, [])


@pytest.mark.parametrize(
    ("code", "returncode", "stderr"),
    [
        pytest.param(None, 0, "", id="none"),
        pytest.param(0, 0, "", id="zero"),
        pytest.param(3, 3, "", id="int"),
        pytest.param("message", 1, "message\n", id="str"),
    ],
)
def test_system_exit_in_command_becomes_the_returncode(
    code: int | str | None, returncode: int, stderr: str
) -> None:
    @command("stop")
    def stop() -> None:
        raise SystemExit(code)

    result = run(stop, [])

    assert result.returncode == returncode
    assert result.stdout == ""
    assert result.stderr == stderr


def test_system_exit_in_group_callback_stops_the_command() -> None:
    calls: list[str] = []

    @group("notes")
    def notes() -> None:
        raise SystemExit(4)

    @command("list_notes")
    def list_notes() -> None:
        calls.append("list_notes")

    notes.add(list_notes)

    result = run(notes, ["list-notes"])

    assert calls == []
    assert result.returncode == 4
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("argv", "code", "output"),
    [
        pytest.param(["greet.py", "Ada"], 0, ("Hello, Ada!\n", ""), id="success"),
        pytest.param(
            ["greet.py"],
            2,
            ("", "error: NAME is required.\nRun 'greet --help' for usage.\n"),
            id="invalid",
        ),
    ],
)
def test_calling_the_cli_runs_sys_argv_and_exits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    code: int,
    output: tuple[str, str],
) -> None:
    @command("greet")
    @argument("name")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as info:
        greet()

    assert info.value.code == code
    assert capsys.readouterr() == output


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        pytest.param(3, 3, id="int"),
        pytest.param("message", "message", id="str"),
    ],
)
def test_calling_the_cli_passes_the_commands_system_exit_through(
    monkeypatch: pytest.MonkeyPatch, code: int | str, expected: int | str
) -> None:
    @command("stop")
    def stop() -> None:
        raise SystemExit(code)

    monkeypatch.setattr(sys, "argv", ["stop.py"])

    with pytest.raises(SystemExit) as info:
        stop()

    assert info.value.code == expected


def test_calling_the_cli_lets_an_uncaught_exception_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @command("fail")
    def fail() -> None:
        message = "disk full"
        raise RuntimeError(message)

    monkeypatch.setattr(sys, "argv", ["fail.py"])

    with pytest.raises(RuntimeError, match="disk full"):
        fail()


def test_run_returns_a_completed_process_with_the_given_args() -> None:
    @command("greet")
    @argument("name")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    result = run(greet, ["Ada"])

    assert type(result) is subprocess.CompletedProcess
    assert cast("list[str]", result.args) == ["Ada"]


def test_run_restores_stdout_and_stderr() -> None:
    @command("greet")
    def greet() -> str:
        return "Hello!"

    stdout, stderr = sys.stdout, sys.stderr

    _ = run(greet, [])

    assert sys.stdout is stdout
    assert sys.stderr is stderr


def test_run_restores_stdout_and_stderr_when_an_exception_propagates() -> None:
    @command("fail")
    def fail() -> None:
        message = "disk full"
        raise RuntimeError(message)

    stdout, stderr = sys.stdout, sys.stderr

    with pytest.raises(RuntimeError, match="disk full"):
        _ = run(fail, [])

    assert sys.stdout is stdout
    assert sys.stderr is stderr


def test_str_enum_member_is_printed_as_its_value() -> None:
    color = Enum("Color", {"RED": "red"}, type=str)

    @command("pick")
    def pick() -> object:
        return color["RED"]

    result = run(pick, [])

    assert (result.returncode, result.stdout, result.stderr) == (0, "red\n", "")


def test_run_gives_the_cli_binary_streams_with_an_encoding() -> None:
    @command("dump")
    def dump() -> None:
        _ = sys.stdout.write(f"{sys.stdout.encoding}\n")
        _ = sys.stdout.buffer.write(b"\xc3\xa9\n")
        _ = sys.stderr.buffer.write(b"done\n")

    result = run(dump, [])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "utf-8\n\u00e9\n",
        "done\n",
    )


def test_run_escapes_unencodable_text_on_stderr_as_python_does() -> None:
    @command("greet")
    @flag("shout")
    def greet(*, shout: bool = False) -> str:
        return str(shout)

    result = run(greet, ["--\udcff"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '--\\udcff'.\nRun 'greet --help' for usage.\n",
    )


def test_run_keeps_bytes_that_arent_utf_8() -> None:
    @command("dump")
    def dump() -> None:
        _ = sys.stdout.buffer.write(b"\x89PNG\n")

    result = run(dump, [])

    assert result.returncode == 0
    assert result.stdout.encode(errors="surrogateescape") == b"\x89PNG\n"
