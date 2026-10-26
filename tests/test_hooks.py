import re
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TypeVar

import pytest

from cliron import Context, between, command, flag, group, hook, on, option, state
from cliron.testing import run, validate

F = TypeVar("F", bound=Callable[..., object])


@state
class Log:
    events: tuple[str, ...] = ()

    def add(self, event: str) -> None:
        self.events = (*self.events, event)


SEEN: list[tuple[str, ...]] = []


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def remember(log: Log) -> None:
    SEEN.append(log.events)


def note(event: str) -> Callable[[Log], None]:
    def add(log: Log) -> None:
        log.add(event)

    return add


def fail(message: str) -> Callable[[], None]:
    def raise_it() -> None:
        raise RuntimeError(message)

    return raise_it


@pytest.fixture(autouse=True)
def fresh() -> None:
    SEEN.clear()


def test_hooks_run_around_a_command_in_the_order_written() -> None:
    @command("work")
    @hook(on.start(), note("start 1"))
    @hook(on.exit(), note("exit"))
    @hook(on.exit(), remember)
    @hook(on.success(), note("success"))
    @hook(on.start(), note("start 2"))
    def work(log: Log) -> str:
        log.add("work")
        return "Done."

    assert run(work, []).stdout == "Done.\n"
    assert SEEN == [("start 1", "start 2", "work", "success", "exit")]


def test_a_groups_hooks_wrap_everything_inside_it_including_teardown() -> None:
    @group("outer")
    @hook(on.start(), note("outer start"))
    @hook(on.success(), note("outer success"))
    @hook(on.exit(), note("outer exit"))
    @hook(on.exit(), remember)
    def outer(log: Log) -> Iterator[None]:
        log.add("outer setup")
        yield
        log.add("outer teardown")

    @group("inner")
    @hook(on.start(), note("inner start"))
    @hook(on.exit(), note("inner exit"))
    def inner(log: Log) -> None:
        log.add("inner")

    @command("work")
    @hook(on.start(), note("work start"))
    @hook(on.exit(), note("work exit"))
    def work(log: Log) -> None:
        log.add("work")

    inner.add(work)
    outer.add(inner)

    assert run(outer, ["inner", "work"]).returncode == 0
    assert SEEN == [
        (
            "outer start",
            "outer setup",
            "inner start",
            "inner",
            "work start",
            "work",
            "work exit",
            "inner exit",
            "outer teardown",
            "outer success",
            "outer exit",
        )
    ]


def test_a_failure_skips_success_but_runs_exit() -> None:
    @group("outer")
    @hook(on.success(), note("outer success"))
    @hook(on.exit(), note("outer exit"))
    @hook(on.exit(), remember)
    def outer() -> None: ...

    @command("work")
    @hook(on.success(), note("work success"))
    @hook(on.exit(), note("work exit"))
    def work() -> None:
        message = "disk full"
        raise RuntimeError(message)

    outer.add(work)

    with pytest.raises(RuntimeError, match="disk full"):
        _ = run(outer, ["work"])
    assert SEEN == [("work exit", "outer exit")]


def test_a_failing_start_hook_stops_its_node_and_skips_its_exit() -> None:
    @group("outer")
    @hook(on.exit(), note("outer exit"))
    @hook(on.exit(), remember)
    def outer() -> None: ...

    @command("work")
    @hook(on.start(), fail("not logged in"))
    @hook(on.exit(), note("work exit"))
    def work(log: Log) -> None:
        log.add("work")

    outer.add(work)

    with pytest.raises(RuntimeError, match="not logged in"):
        _ = run(outer, ["work"])
    assert SEEN == [("outer exit",)]


def test_a_failing_success_hook_fails_the_run_and_prints_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @command("work")
    @hook(on.success(), fail("audit failed"))
    @hook(on.exit(), note("exit"))
    @hook(on.exit(), remember)
    def work() -> str:
        return "Done."

    monkeypatch.setattr(sys, "argv", ["work"])

    with pytest.raises(RuntimeError, match="audit failed"):
        work()
    assert capsys.readouterr().out == ""
    assert SEEN == [("exit",)]


def test_a_failing_exit_hook_replaces_the_failure() -> None:
    @command("work")
    @hook(on.exit(), fail("cleanup failed"))
    def work() -> None:
        message = "disk full"
        raise OSError(message)

    with pytest.raises(RuntimeError, match="cleanup failed") as info:
        _ = run(work, [])
    assert isinstance(info.value.__context__, OSError)


@pytest.mark.parametrize("args", [["-x"], ["--help"], ["--version"]])
def test_hooks_dont_run_when_nothing_runs(args: list[str]) -> None:
    @command("work", version="1.0")
    @hook(on.start(), remember)
    @hook(on.exit(), remember)
    def work() -> None: ...

    _ = run(work, args)
    assert SEEN == []


def test_a_hook_receives_the_context_with_every_nodes_values() -> None:
    values: list[object] = []

    def show(ctx: Context) -> None:
        values.append((ctx.path, [dict(each) for each in ctx.values]))

    @group("notes")
    @hook(on.start(), show)
    @flag("quiet", "-q")
    def notes(ctx: Context, *, quiet: bool = False) -> None:
        _ = (ctx, quiet)

    @command("add")
    @option("quiet")
    def add(log: Log, quiet: str = "no") -> str:
        return f"{log.events} {quiet}"

    notes.add(add)

    assert run(notes, ["-q", "add", "--quiet", "yes"]).stdout == "() yes\n"
    assert values == [(("notes", "add"), [{"quiet": True}, {"quiet": "yes"}])]


def test_hooks_can_be_bundled_in_a_decorator() -> None:
    def logged(function: F) -> F:
        return hook(on.start(), note("start"))(hook(on.exit(), remember)(function))

    @command("work")
    @logged
    def work() -> None: ...

    assert run(work, []).returncode == 0
    assert SEEN == [("start",)]


def test_a_hook_that_returns_a_value_is_a_mistake() -> None:
    def answer() -> int:
        return 42

    @command("work")
    @hook(on.start(), answer)
    def work() -> None: ...

    message = "hook function 'answer' returned int, but a hook must return None."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(work, [])


def test_a_hook_below_a_parent_or_child_is_rejected() -> None:
    def work(count: int = 1) -> int:
        return count

    below_parent = hook(on.start(), remember)(work)
    message = (
        '@hook(on.start(), remember) is below @option("count"), so it would attach '
        "to it, but on.start() runs around commands and groups; only on.error() "
        "attaches to parents and children. Move it right below @command or @group, "
        "above the first parent."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("work")(option("count")(below_parent))

    below_child = hook(on.exit(), remember)(work)
    message = (
        "@hook(on.exit(), remember) is below @between(1, 5), so it would attach to "
        "it, but on.exit() runs around commands and groups; only on.error() "
        "attaches to parents and children. Move it right below @command or @group, "
        "above the first parent."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("other")(option("count")(between(1, 5)(below_child)))


def needs_a_value(count: int) -> None:
    _ = count


def takes_twice(first: Log, second: Log) -> None:
    _ = (first, second)


async def repeats_later() -> AsyncIterator[None]:
    yield


def repeats() -> Iterator[None]:
    yield


def positional(log: Log, /) -> None:
    _ = log


@pytest.mark.parametrize(
    ("callback", "message"),
    [
        (
            needs_a_value,
            (
                "hook function 'needs_a_value' takes parameter 'count', but a hook "
                "receives only Context and @state classes. Annotate it with one, "
                "or remove it."
            ),
        ),
        (
            positional,
            (
                "hook function 'positional' takes parameter 'log', but a hook "
                "receives only Context and @state classes. Annotate it with one, "
                "or remove it."
            ),
        ),
        (
            takes_twice,
            "parameters 'first' and 'second' both take Log. Keep one.",
        ),
        (
            repeats_later,
            (
                "hook function 'repeats_later' is a generator. Run code before and "
                "after with on.start() and on.exit() hooks, or yield in a group's "
                "function."
            ),
        ),
        (
            repeats,
            (
                "hook function 'repeats' is a generator. Run code before and after "
                "with on.start() and on.exit() hooks, or yield in a group's function."
            ),
        ),
    ],
    ids=["value", "positional", "twice", "async-generator", "generator"],
)
def test_a_hook_function_that_cant_be_called_is_rejected(
    callback: Callable[..., object], message: str
) -> None:
    def work() -> None: ...

    cli = command("work")(hook(on.start(), callback)(work))

    with pytest.raises(TypeError, match=exactly(message)):
        validate(cli)


@pytest.mark.parametrize(
    ("event", "callback", "message"),
    [
        (on.start, remember, "@hook needs the event called, such as on.start()."),
        (
            "start",
            remember,
            "@hook takes an event first, such as on.start(), not 'start'.",
        ),
        (
            on.exit(),
            "remember",
            (
                "@hook takes a function to run, such as hook(on.start(), "
                "start_timer), not 'remember'."
            ),
        ),
    ],
    ids=["not-called", "not-an-event", "not-a-function"],
)
@pytest.mark.parametrize("make", [hook])
def test_a_wrong_hook_is_rejected(
    make: Callable[..., object], event: object, callback: object, message: str
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = make(event, callback)


def test_a_hook_above_the_root_decorator_is_rejected() -> None:
    @command("work")
    def work() -> None: ...

    above: Callable[..., object] = hook(on.start(), remember)
    message = (
        "@hook(on.start(), remember) must decorate a function, so it goes below "
        "@command or @group."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = above(work)
