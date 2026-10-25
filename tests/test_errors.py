import re
from collections.abc import Callable, Iterator

import pytest

from cliron import command, group, hook, on, option, state
from cliron.testing import run, validate


@state
class Log:
    events: tuple[str, ...] = ()

    def add(self, event: str) -> None:
        self.events = (*self.events, event)


SEEN: list[tuple[str, ...]] = []


@pytest.fixture(autouse=True)
def fresh() -> None:
    SEEN.clear()


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def remember(log: Log) -> None:
    SEEN.append(log.events)


def note(event: str) -> Callable[[Log], None]:
    def add(log: Log) -> None:
        log.add(event)

    return add


def raise_timeout() -> str:
    message = "too slow"
    raise TimeoutError(message)


def use_cache(exc: TimeoutError, log: Log) -> str:
    log.add(f"handled {exc}")
    return "cached"


def test_a_commands_handler_replaces_its_result() -> None:
    @command("weather")
    @hook(on.error(), use_cache)
    @hook(on.success(), note("success"))
    @hook(on.exit(), remember)
    def weather() -> str:
        return raise_timeout()

    result = run(weather, [])

    assert (result.returncode, result.stdout) == (0, "cached\n")
    assert SEEN == [("handled too slow", "success")]


def test_a_groups_handler_handles_what_fails_inside_after_teardown() -> None:
    def explain(exc: FileNotFoundError, log: Log) -> None:
        log.add(f"no such file: {exc}")

    @group("files")
    @hook(on.error(), explain)
    @hook(on.exit(), remember)
    def files(log: Log) -> Iterator[None]:
        try:
            yield
        finally:
            log.add("teardown")

    @command("show")
    def show() -> str:
        message = "notes.txt"
        raise FileNotFoundError(message)

    files.add(show)

    result = run(files, ["show"])

    assert (result.returncode, result.stdout) == (0, "")
    assert SEEN == [("teardown", "no such file: notes.txt")]


def test_a_handler_can_end_the_run_with_an_exit_code() -> None:
    def give_up(exc: TimeoutError) -> None:
        raise SystemExit(1) from exc

    @command("weather")
    @hook(on.error(), give_up)
    def weather() -> str:
        return raise_timeout()

    assert run(weather, []).returncode == 1


def test_the_annotation_selects_the_exceptions_a_handler_takes() -> None:
    def lookup(exc: KeyError | IndexError) -> str:
        return f"missing {type(exc).__name__}"

    @command("find")
    @hook(on.error(), lookup)
    @option("kind")
    def find(kind: str) -> str:
        if kind == "key":
            raise KeyError(kind)
        if kind == "index":
            raise IndexError(kind)
        raise ValueError(kind)

    assert run(find, ["--kind", "key"]).stdout == "missing KeyError\n"
    assert run(find, ["--kind", "index"]).stdout == "missing IndexError\n"
    with pytest.raises(ValueError, match="other"):
        _ = run(find, ["--kind", "other"])


def test_the_first_matching_handler_runs_and_one_that_raises_passes_it_out() -> None:
    def first(exc: TimeoutError, log: Log) -> str:
        log.add("first")
        raise exc

    def second(exc: TimeoutError, log: Log) -> str:
        log.add(f"second {exc}")
        return "second"

    def outer_handler(exc: TimeoutError, log: Log) -> None:
        log.add(f"outer {exc}")

    @group("tool")
    @hook(on.error(), outer_handler)
    @hook(on.exit(), remember)
    def tool() -> None: ...

    @command("weather")
    @hook(on.error(), first)
    @hook(on.error(), second)
    def weather() -> str:
        return raise_timeout()

    tool.add(weather)

    assert run(tool, ["weather"]).stdout == ""
    assert SEEN == [("first", "outer too slow")]


def test_a_handler_that_raises_something_else_replaces_the_exception() -> None:
    def translate(exc: TimeoutError) -> str:
        message = "the weather service didn't answer"
        raise RuntimeError(message) from exc

    @command("weather")
    @hook(on.error(), translate)
    def weather() -> str:
        return raise_timeout()

    with pytest.raises(RuntimeError, match="didn't answer") as info:
        _ = run(weather, [])
    assert isinstance(info.value.__cause__, TimeoutError)


def test_a_handler_covers_its_nodes_start_hooks_but_not_its_success_hooks() -> None:
    def check_login() -> None:
        message = "not logged in"
        raise PermissionError(message)

    def audit() -> None:
        message = "audit failed"
        raise PermissionError(message)

    def explain(exc: PermissionError, log: Log) -> str:
        log.add(f"handled {exc}")
        return "Log in first."

    @command("deploy")
    @hook(on.start(), check_login)
    @hook(on.error(), explain)
    @hook(on.exit(), remember)
    def deploy() -> str:
        return "Deployed."

    @command("publish")
    @hook(on.success(), audit)
    @hook(on.error(), explain)
    @hook(on.exit(), remember)
    def publish() -> str:
        return "Published."

    assert run(deploy, []).stdout == "Log in first.\n"
    assert SEEN == []
    with pytest.raises(PermissionError, match="audit failed"):
        _ = run(publish, [])
    assert SEEN == [()]


def test_ctrl_c_and_definition_mistakes_pass_every_handler() -> None:
    def everything(exc: Exception) -> None:
        _ = exc

    @group("tool")
    @hook(on.error(), everything)
    def tool() -> None: ...

    @group("broken")
    def broken() -> int:
        return 1

    @command("stop")
    def stop() -> None:
        raise KeyboardInterrupt

    broken.add(command("inside")(lambda: None))
    tool.add(stop, broken)

    with pytest.raises(KeyboardInterrupt):
        _ = run(tool, ["stop"])
    with pytest.raises(TypeError, match="group 'broken' returned int"):
        _ = run(tool, ["broken", "inside"])


def test_a_handler_must_return_what_its_node_would() -> None:
    def wrong(exc: TimeoutError) -> object:
        return len(str(exc))

    def anything(exc: TimeoutError) -> object:
        return len(str(exc))

    @command("weather")
    @hook(on.error(), wrong)
    def weather() -> str:
        return raise_timeout()

    def loose() -> str:
        return raise_timeout()

    del loose.__annotations__["return"]
    unannotated = command("loose")(hook(on.error(), anything)(loose))

    @command("quiet")
    @hook(on.error(), wrong)
    def quiet() -> None:
        _ = raise_timeout()

    @group("tool")
    @hook(on.error(), wrong)
    def tool() -> None:
        _ = raise_timeout()

    tool.add(command("inside")(lambda: None))

    message = (
        "hook function 'wrong' returned int, but command 'weather' returns str. "
        "Make it return str."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(weather, [])
    assert run(unannotated, []).stdout == "8\n"
    message = (
        "hook function 'wrong' returned int, but command 'quiet' returns None. "
        "Make it return None."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(quiet, [])
    message = (
        "hook function 'wrong' returned int, but group 'tool' has no result to "
        "replace. Return None."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(tool, ["inside"])


def handles_nothing(log: Log) -> None:
    _ = log


def handles_two(first: KeyError, second: ValueError) -> None:
    _ = (first, second)


def handles_ctrl_c(exc: KeyboardInterrupt) -> None:
    _ = exc


def handles_everything(exc: ValueError | BaseException) -> None:
    _ = exc


def handles_a_value(exc: ValueError, count: int) -> None:
    _ = (exc, count)


def starts_with_an_exception(exc: ValueError) -> None:
    _ = exc


@pytest.mark.parametrize(
    ("event", "callback", "message"),
    [
        (
            on.error(),
            handles_nothing,
            (
                "hook function 'handles_nothing' handles no exception. Annotate one "
                "parameter with the exceptions it handles, such as exc: ValueError."
            ),
        ),
        (
            on.error(),
            handles_two,
            (
                "hook function 'handles_two' takes two exceptions, 'first' and "
                "'second'. Annotate one parameter, with a union for several, such "
                "as exc: ValueError | KeyError."
            ),
        ),
        (
            on.error(),
            handles_ctrl_c,
            (
                "hook function 'handles_ctrl_c' handles KeyboardInterrupt, which "
                "cliron always lets through so that Ctrl+C and exits work. Handle "
                "Exception or a subclass of it."
            ),
        ),
        (
            on.error(),
            handles_everything,
            (
                "hook function 'handles_everything' handles BaseException, which "
                "cliron always lets through so that Ctrl+C and exits work. Handle "
                "Exception or a subclass of it."
            ),
        ),
        (
            on.error(),
            handles_a_value,
            (
                "hook function 'handles_a_value' takes parameter 'count', but a hook "
                "receives only an exception, Context and @state classes. Annotate "
                "it with one, or remove it."
            ),
        ),
        (
            on.start(),
            starts_with_an_exception,
            (
                "hook function 'starts_with_an_exception' takes the exception 'exc', "
                "but only on.error() hooks receive one."
            ),
        ),
    ],
    ids=["none", "two", "ctrl-c", "base", "value", "start"],
)
@pytest.mark.parametrize("attach", [hook])
def test_a_handler_that_cant_be_called_is_rejected(
    attach: Callable[..., Callable[[Callable[..., object]], Callable[..., object]]],
    event: object,
    callback: Callable[..., object],
    message: str,
) -> None:
    def work() -> None: ...

    cli = command("work")(attach(event, callback)(work))

    with pytest.raises(TypeError, match=exactly(message)):
        validate(cli)
