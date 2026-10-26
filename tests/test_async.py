import asyncio
import os
import re
import signal
import subprocess
import sys
from collections.abc import AsyncIterator, Coroutine
from pathlib import Path

import pytest

from cliron import (
    Child,
    Parent,
    argument,
    child,
    command,
    group,
    hook,
    on,
    option,
    parent,
    state,
)
from cliron.testing import run, validate

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")

SYNC_RUN = """\
import sys

from cliron import command
from cliron.testing import run


@command("greet")
def greet() -> str:
    return "Hello!"


assert run(greet, []).stdout == "Hello!\\n"
assert run(greet, ["--help"]).returncode == 0
print("asyncio" in sys.modules)
"""

SERVE = """\
import asyncio

from cliron import command


@command("serve")
async def serve() -> None:
    try:
        print("ready", flush=True)
        await asyncio.sleep(60)
    finally:
        print("cleaned up", flush=True)


serve()
"""


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


async def remember(log: Log) -> None:
    await asyncio.sleep(0)
    SEEN.append(log.events)


def started(log: Log) -> None:
    log.add("start")


@child
async def doubled(value: int) -> int:
    await asyncio.sleep(0)
    return value * 2


class Even(Child[int, int]):
    async def process(self, value: int, /) -> int:
        await asyncio.sleep(0)
        if value % 2:
            message = f"{value} isn't even."
            raise ValueError(message)
        return value


@parent
async def secret(name: str) -> str | None:
    await asyncio.sleep(0)
    return f"secret-{name}"


class Remote(Parent):
    async def load(self) -> str | None:
        await asyncio.sleep(0)
        return None


async def nearest_even(exc: ValueError) -> int:
    _ = exc
    await asyncio.sleep(0)
    return 0


def test_an_async_command_runs_and_its_result_is_printed() -> None:
    @command("fetch")
    @argument("urls")
    async def fetch(urls: list[str]) -> dict[str, int]:
        sizes = await asyncio.gather(*(asyncio.sleep(0, len(url)) for url in urls))
        return dict(zip(urls, sizes, strict=True))

    assert run(fetch, ["a", "bcd"]).stdout == '{\n  "a": 1,\n  "bcd": 3\n}\n'


def test_sync_and_async_mix_in_one_run_with_the_same_order() -> None:
    @group("api")
    @hook(on.start(), started)
    @hook(on.exit(), remember)
    async def api(log: Log) -> AsyncIterator[None]:
        log.add("setup")
        try:
            yield
        finally:
            log.add("teardown")

    @command("show")
    def show(log: Log) -> str:
        log.add("show")
        return "Shown."

    api.add(show)

    assert run(api, ["show"]).stdout == "Shown.\n"
    assert SEEN == [("start", "setup", "show", "teardown")]


def test_an_async_teardown_sees_the_failure_and_cant_swallow_it() -> None:
    @group("api")
    @hook(on.exit(), remember)
    async def api(log: Log) -> AsyncIterator[None]:
        try:
            yield
        except RuntimeError as error:
            log.add(f"saw {error}")

    @command("fail")
    async def fail() -> None:
        await asyncio.sleep(0)
        message = "down"
        raise RuntimeError(message)

    api.add(fail)

    with pytest.raises(RuntimeError, match="down"):
        _ = run(api, ["fail"])
    assert SEEN == [("saw down",)]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "early",
            (
                "group 'api' returned before its yield, so nothing inside it could "
                "run. Yield once, between setup and teardown."
            ),
        ),
        (
            "value",
            (
                "group 'api' yielded str, but a group yields nothing. Use a bare "
                "yield, and share data with @state."
            ),
        ),
        ("twice", "group 'api' yielded twice. Yield once, between setup and teardown."),
    ],
)
def test_an_async_group_that_yields_wrongly_is_a_mistake(
    body: str, message: str
) -> None:
    async def api() -> AsyncIterator[object]:
        if body == "early":
            return
        if body == "value":
            yield "client"
        yield
        yield

    cli = group("api")(api)
    cli.add(command("show")(lambda: None))

    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(cli, ["show"])


def test_an_async_group_must_return_none() -> None:
    async def api() -> object:
        await asyncio.sleep(0)
        return 1

    cli = group("api")(api)
    cli.add(command("show")(lambda: None))

    message = (
        "group 'api' returned int, but a group must return None. "
        "Print the value, or return it from a command."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(cli, ["show"])


def test_async_children_parents_and_handlers_run() -> None:
    @command("show")
    @option("count")
    @doubled()
    @Even()
    @hook(on.error(), nearest_even)
    @secret("token")
    @Remote("region")
    def show(count: int, token: str, region: str = "eu") -> str:
        return f"{count} {token} {region}"

    assert run(show, ["--count", "3"]).stdout == "6 secret-token eu\n"


def test_an_async_handler_replaces_a_result() -> None:
    async def cached(exc: TimeoutError) -> str:
        await asyncio.sleep(0)
        return f"cached after {exc}"

    @command("weather")
    @hook(on.error(), cached)
    async def weather() -> str:
        message = "slow"
        raise TimeoutError(message)

    assert run(weather, []).stdout == "cached after slow\n"


def test_an_async_childs_default_is_checked_on_each_run() -> None:
    @command("pick")
    @option("count")
    @Even()
    def pick(count: int = 3) -> int:
        return count

    validate(pick)
    assert run(pick, []).stderr == (
        "error: --count: 3 isn't even.\nRun 'pick --help' for usage.\n"
    )


def test_a_sync_run_never_imports_asyncio(tmp_path: Path) -> None:
    script = tmp_path / "greet.py"
    _ = script.write_text(SYNC_RUN, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=True
    )

    assert result.stdout == "False\n"


def test_an_async_cli_inside_a_running_loop_is_an_error() -> None:
    @command("fetch")
    async def fetch() -> str:
        return "fetched"

    @command("greet")
    def greet() -> str:
        return "Hello!"

    async def inside() -> str:
        assert run(greet, []).stdout == "Hello!\n"
        return run(fetch, []).stdout

    message = (
        "cliron runs async functions in an event loop of its own, but one is "
        "already running in this thread. Call the CLI from synchronous code, such "
        "as a test that isn't async."
    )
    with pytest.raises(RuntimeError, match=exactly(message)):
        _ = asyncio.run(inside())


def test_waiting_for_a_loop_without_an_async_function_is_an_error() -> None:
    @command("wait")
    def wait() -> Coroutine[object, object, None]:
        return asyncio.sleep(0)

    message = (
        "something on this command line returned a value to await that waits for "
        "an event loop, but no function, hook, child or parent on it is async def. "
        "Make the one that waits async def."
    )
    with pytest.raises(RuntimeError, match=exactly(message)):
        _ = run(wait, [])


@POSIX
@pytest.mark.parametrize(
    ("number", "raised"),
    [(signal.SIGTERM, SystemExit), (signal.SIGINT, KeyboardInterrupt)],
    ids=["sigterm", "ctrl-c"],
)
def test_a_signal_cancels_the_async_run_and_cleanup_runs(
    monkeypatch: pytest.MonkeyPatch,
    number: signal.Signals,
    raised: type[BaseException],
) -> None:
    @group("serve")
    @hook(on.exit(), remember)
    async def serve(log: Log) -> AsyncIterator[None]:
        try:
            yield
        finally:
            log.add("teardown")

    @command("forever")
    async def forever(log: Log) -> None:
        try:
            os.kill(os.getpid(), number)
            await asyncio.sleep(10)
        finally:
            log.add("cancelled")

    serve.add(forever)
    monkeypatch.setattr(sys, "argv", ["serve", "forever"])

    with pytest.raises(raised) as info:
        serve()
    if isinstance(info.value, SystemExit):
        assert info.value.code == 143
    assert SEEN == [("cancelled", "teardown")]
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


@POSIX
@pytest.mark.parametrize(
    ("number", "returncode"), [(signal.SIGINT, -signal.SIGINT), (signal.SIGTERM, 143)]
)
def test_a_real_async_process_stops_cleanly_on_a_signal(
    tmp_path: Path, number: signal.Signals, returncode: int
) -> None:
    script = tmp_path / "serve.py"
    _ = script.write_text(SERVE, encoding="utf-8")
    with subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout is not None
            assert process.stdout.readline() == "ready\n"
            process.send_signal(number)
            stdout, stderr = process.communicate(timeout=10)
        finally:
            process.kill()

    assert (process.returncode, stdout, stderr) == (returncode, "cleaned up\n", "")
