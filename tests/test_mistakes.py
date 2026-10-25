import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from cliron import command, group, option
from cliron.testing import run


def call(
    cli: Callable[[], object], argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> SystemExit:
    monkeypatch.setattr(sys, "argv", ["cli.py", *argv])
    with pytest.raises(SystemExit) as info:
        _ = cli()
    return info.value


def where(kind: str, name: str, line: int) -> str:
    return f"in {kind} '{name}', defined at {__file__}:{line}"


def test_a_definition_mistake_is_printed_with_where_it_is(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def add(tag: str) -> None:
        _ = tag

    cli = command("add")(add)

    exit_ = call(cli, [], monkeypatch)

    assert exit_.code == 1
    assert capsys.readouterr() == (
        "",
        (
            "error: parameter 'tag' has no parent. Add one above the function, "
            'for example @option("tag").\n'
            f"  {where('command', 'add', add.__code__.co_firstlineno)}\n"
        ),
    )


def test_a_mistake_in_a_nested_command_names_that_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @group("notes")
    def notes() -> None: ...

    def add(tag: str) -> None:
        _ = tag

    notes.add(command("add")(add))

    exit_ = call(notes, ["add"], monkeypatch)

    assert exit_.code == 1
    assert capsys.readouterr().err.endswith(
        f"  {where('command', 'add', add.__code__.co_firstlineno)}\n"
    )


def test_an_annotation_that_names_nothing_is_printed_with_where_it_is(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def add(tag: str) -> None:
        _ = tag

    add.__annotations__["tag"] = "Missing"
    cli = command("add")(option("tag")(add))

    exit_ = call(cli, [], monkeypatch)

    assert exit_.code == 1
    assert capsys.readouterr().err == (
        "error: name 'Missing' is not defined\n"
        f"  {where('command', 'add', add.__code__.co_firstlineno)}\n"
    )


def test_a_group_returning_a_value_is_printed_with_where_it_is(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def notes() -> str:
        return "done"

    @command("list")
    def list_notes() -> None: ...

    cli = group("notes")(notes)
    cli.add(list_notes)

    exit_ = call(cli, ["list"], monkeypatch)

    assert exit_.code == 1
    assert capsys.readouterr().err == (
        "error: group 'notes' returned str, but a group must return None. "
        "Print the value, or return it from a command.\n"
        f"  {where('group', 'notes', notes.__code__.co_firstlineno)}\n"
    )


def test_a_return_value_json_cant_represent_is_printed_with_where_it_is(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def show() -> Path:
        return Path("notes.db")

    cli = command("show")(show)

    exit_ = call(cli, [], monkeypatch)

    assert exit_.code == 1
    assert capsys.readouterr() == (
        "",
        (
            f"error: Object of type {type(Path()).__name__} is not JSON serializable\n"
            "  Return None, a str, or data that JSON can represent.\n"
            f"  {where('command', 'show', show.__code__.co_firstlineno)}\n"
        ),
    )


def test_an_exception_from_the_command_itself_keeps_its_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @command("fail")
    def fail() -> None:
        message = "the command's own bug"
        raise RuntimeError(message)

    monkeypatch.setattr(sys, "argv", ["cli.py"])

    with pytest.raises(RuntimeError, match="the command's own bug"):
        fail()


def test_testing_run_raises_the_original_mistake() -> None:
    def add(tag: str) -> None:
        _ = tag

    cli = command("add")(add)

    with pytest.raises(TypeError, match="parameter 'tag' has no parent") as info:
        _ = run(cli, [])

    assert info.value.__notes__ == [
        where("command", "add", add.__code__.co_firstlineno)
    ]
    assert info.value.__suppress_context__
