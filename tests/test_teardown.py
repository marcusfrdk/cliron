import re
import sys
from collections.abc import Generator, Iterator

import pytest

from cliron import command, group
from cliron.testing import run


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def test_setup_runs_top_down_and_teardown_innermost_first() -> None:
    events: list[str] = []

    @group("outer")
    def outer() -> Iterator[None]:
        events.append("outer setup")
        yield
        events.append("outer teardown")

    @group("inner")
    def inner() -> Iterator[None]:
        events.append("inner setup")
        yield
        _ = sys.stdout.write("inner teardown\n")
        events.append("inner teardown")

    @command("work")
    def work() -> str:
        events.append("work")
        return "Done."

    inner.add(work)
    outer.add(inner)

    assert run(outer, ["inner", "work"]).stdout == "inner teardown\nDone.\n"
    assert events == [
        "outer setup",
        "inner setup",
        "work",
        "inner teardown",
        "outer teardown",
    ]


def test_a_failure_is_raised_at_every_yield_on_its_way_out() -> None:
    events: list[str] = []

    @group("outer")
    def outer() -> Iterator[None]:
        try:
            yield
        except RuntimeError as error:
            events.append(f"outer saw {error}")
            raise

    @group("inner")
    def inner() -> Iterator[None]:
        try:
            yield
        finally:
            events.append("inner closed")

    @command("work")
    def work() -> str:
        message = "disk full"
        raise RuntimeError(message)

    inner.add(work)
    outer.add(inner)

    with pytest.raises(RuntimeError, match="disk full"):
        _ = run(outer, ["inner", "work"])
    assert events == ["inner closed", "outer saw disk full"]


def test_a_teardown_cant_swallow_the_failure() -> None:
    events: list[str] = []

    @group("outer")
    def outer() -> Iterator[None]:
        try:
            yield
        except RuntimeError:
            events.append("outer saw it")
            raise

    @group("inner")
    def inner() -> Iterator[None]:
        try:
            yield
        except RuntimeError:
            events.append("inner swallowed it")

    @command("work")
    def work() -> str:
        message = "disk full"
        raise RuntimeError(message)

    inner.add(work)
    outer.add(inner)

    with pytest.raises(RuntimeError, match="disk full"):
        _ = run(outer, ["inner", "work"])
    assert events == ["inner swallowed it", "outer saw it"]


def test_a_failing_teardown_replaces_the_failure_and_reaches_outer_groups() -> None:
    events: list[str] = []

    @group("outer")
    def outer() -> Iterator[None]:
        try:
            yield
        except OSError as error:
            events.append(f"outer saw {error}")
            raise

    @group("inner")
    def inner() -> Iterator[None]:
        try:
            yield
        except RuntimeError as error:
            message = "rollback failed"
            raise OSError(message) from error

    @command("work")
    def work() -> str:
        message = "disk full"
        raise RuntimeError(message)

    inner.add(work)
    outer.add(inner)

    with pytest.raises(OSError, match="rollback failed") as info:
        _ = run(outer, ["inner", "work"])
    assert isinstance(info.value.__cause__, RuntimeError)
    assert events == ["outer saw rollback failed"]


def test_output_is_printed_only_after_every_teardown_succeeded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @group("notes")
    def notes() -> Iterator[None]:
        yield
        message = "commit failed"
        raise OSError(message)

    @command("add")
    def add() -> str:
        return "Added note 1."

    notes.add(add)
    monkeypatch.setattr(sys, "argv", ["notes", "add"])

    with pytest.raises(OSError, match="commit failed"):
        notes()
    assert capsys.readouterr().out == ""


def test_ctrl_c_still_runs_the_teardown() -> None:
    events: list[str] = []

    @group("serve")
    def serve() -> Iterator[None]:
        try:
            yield
        finally:
            events.append("closed")

    @command("forever")
    def forever() -> None:
        raise KeyboardInterrupt

    serve.add(forever)

    with pytest.raises(KeyboardInterrupt):
        _ = run(serve, ["forever"])
    assert events == ["closed"]


def test_a_group_that_returns_before_its_yield_is_a_mistake() -> None:
    @group("notes")
    def notes() -> Iterator[None]:
        yield from ()

    @command("add")
    def add() -> str:
        return "Added."

    notes.add(add)

    message = (
        "group 'notes' returned before its yield, so nothing inside it could run. "
        "Yield once, between setup and teardown."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(notes, ["add"])


def test_a_group_that_yields_a_value_is_a_mistake() -> None:
    events: list[str] = []

    @group("outer")
    def outer() -> Iterator[None]:
        try:
            yield
        finally:
            events.append("outer closed")

    @group("notes")
    def notes() -> Iterator[str]:
        try:
            yield "connection"
        finally:
            events.append("notes closed")

    @command("add")
    def add() -> str:
        return "Added."

    notes.add(add)
    outer.add(notes)

    message = (
        "group 'notes' yielded str, but a group yields nothing. "
        "Use a bare yield, and share data with @state."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(outer, ["notes", "add"])
    assert events == ["notes closed", "outer closed"]


def test_a_group_that_yields_twice_is_a_mistake() -> None:
    events: list[str] = []

    @group("notes")
    def notes() -> Iterator[None]:
        try:
            yield
            yield
        finally:
            events.append("closed")

    @command("add")
    def add() -> str:
        return "Added."

    notes.add(add)

    message = "group 'notes' yielded twice. Yield once, between setup and teardown."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(notes, ["add"])
    assert events == ["closed"]


def test_a_group_that_returns_a_value_after_its_yield_is_a_mistake() -> None:
    @group("notes")
    def notes() -> Generator[None, None, int]:
        yield
        return 1

    @command("add")
    def add() -> str:
        return "Added."

    notes.add(add)

    message = (
        "group 'notes' returned int, but a group must return None. "
        "Print the value, or return it from a command."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(notes, ["add"])
