import io
import os
import select
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from types import FrameType, TracebackType
from typing import cast

import pytest

from cliron import command
from cliron.testing import run

POSIX = pytest.mark.skipif(
    sys.platform == "win32", reason="needs POSIX signals and pipes"
)

SERVE = """\
import sys
import time

from cliron import command, flag


@command("serve")
@flag("crash")
def serve(*, crash: bool = False) -> None:
    try:
        print("ready", flush=True)
        if crash:
            raise ValueError("boom")
        time.sleep(60)
    finally:
        print("cleaned up", flush=True)


serve()
"""

PENDING = """\
import time

from cliron import command


@command("pending")
def pending() -> None:
    print("ready", flush=True)
    print("still buffered")
    time.sleep(60)


pending()
"""

MANY = """\
from cliron import command


@command("many")
def many() -> str:
    return "\\n".join(str(number) for number in range(200000))


many()
"""


def ctrl_break() -> int:
    if sys.platform == "win32":
        return signal.SIGBREAK
    return signal.SIGUSR1


@pytest.fixture(autouse=True)
def default_handlers() -> Iterator[None]:
    numbers = [signal.SIGTERM, ctrl_break()]
    previous = {number: signal.signal(number, signal.SIG_DFL) for number in numbers}
    yield
    for number, handler in previous.items():
        _ = signal.signal(number, handler)


def raise_if_handled(number: int) -> None:
    if callable(signal.getsignal(number)):
        signal.raise_signal(number)


def call(cli: Callable[[], object], monkeypatch: pytest.MonkeyPatch) -> SystemExit:
    monkeypatch.setattr(sys, "argv", ["cli"])
    with pytest.raises(SystemExit) as info:
        _ = cli()
    return info.value


def broken_pipe() -> io.TextIOWrapper:
    read_end, write_end = os.pipe()
    os.close(read_end)
    return os.fdopen(write_end, "w", buffering=1)


def test_ctrl_c_runs_cleanup_and_hides_only_its_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    printed: list[type[BaseException]] = []

    def excepthook(
        kind: type[BaseException], error: BaseException, traceback: TracebackType | None
    ) -> None:
        _ = (error, traceback)
        printed.append(kind)

    @command("serve")
    def serve() -> None:
        try:
            raise KeyboardInterrupt
        finally:
            calls.append("cleanup")

    monkeypatch.setattr(sys, "excepthook", excepthook)
    monkeypatch.setattr(sys, "argv", ["serve"])
    with pytest.raises(KeyboardInterrupt) as info:
        _ = serve()
    sys.excepthook(KeyboardInterrupt, info.value, None)
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    sys.excepthook(ValueError, ValueError("boom"), None)

    assert calls == ["cleanup"]
    assert printed == [KeyboardInterrupt, ValueError]


def test_sigterm_runs_cleanup_and_exits_with_143(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    excepthook = sys.excepthook

    @command("serve")
    def serve() -> None:
        try:
            raise_if_handled(signal.SIGTERM)
        finally:
            calls.append("cleanup")

    exit_ = call(serve, monkeypatch)

    assert exit_.code == 143
    assert calls == ["cleanup"]
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    assert sys.excepthook is excepthook


def test_sigterm_during_cleanup_exits_with_143_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes: list[object] = []

    @command("serve")
    def serve() -> None:
        try:
            raise_if_handled(signal.SIGTERM)
        finally:
            try:
                raise_if_handled(signal.SIGTERM)
            except SystemExit as exit_:
                codes.append(exit_.code)

    exit_ = call(serve, monkeypatch)

    assert exit_.code == 143
    assert codes == [143]


def test_handlers_and_excepthook_are_restored_after_a_normal_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    during: list[object] = []
    excepthook = sys.excepthook

    @command("probe")
    def probe() -> str:
        during.append(signal.getsignal(signal.SIGTERM))
        return "done"

    exit_ = call(probe, monkeypatch)

    assert exit_.code == 0
    assert during != [signal.SIG_DFL]
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    assert sys.excepthook is excepthook


def test_off_the_main_thread_no_handler_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    during: list[object] = []
    codes: list[object] = []

    @command("probe")
    def probe() -> None:
        during.append(signal.getsignal(signal.SIGTERM))

    def target() -> None:
        try:
            _ = probe()
        except SystemExit as exit_:
            codes.append(exit_.code)

    monkeypatch.setattr(sys, "argv", ["probe"])
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()

    assert codes == [0]
    assert during == [signal.SIG_DFL]


@pytest.mark.parametrize("error", [KeyboardInterrupt, BrokenPipeError])
def test_off_the_main_thread_errors_pass_through_unchanged(
    monkeypatch: pytest.MonkeyPatch, error: type[BaseException]
) -> None:
    caught: list[type[BaseException]] = []
    excepthook = sys.excepthook

    @command("fail")
    def fail() -> None:
        raise error

    def target() -> None:
        try:
            _ = fail()
        except (KeyboardInterrupt, BrokenPipeError) as exception:
            caught.append(type(exception))

    monkeypatch.setattr(sys, "argv", ["fail"])
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()

    assert caught == [error]
    assert sys.excepthook is excepthook


def test_ctrl_break_is_handled_like_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    number = ctrl_break()
    monkeypatch.setattr(signal, "SIGBREAK", number, raising=False)

    @command("serve")
    def serve() -> None:
        raise_if_handled(number)

    exit_ = call(serve, monkeypatch)

    assert exit_.code == 143
    assert signal.getsignal(number) is signal.SIG_DFL


def test_a_handler_installed_outside_python_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    getsignal = signal.getsignal
    during: list[object] = []

    def outside(number: int) -> object:
        return None if number == signal.SIGTERM else getsignal(number)

    @command("probe")
    def probe() -> None:
        during.append(getsignal(signal.SIGTERM))

    monkeypatch.setattr(signal, "getsignal", outside)
    exit_ = call(probe, monkeypatch)

    assert exit_.code == 0
    assert during == [signal.SIG_DFL]


def test_a_sigterm_handler_set_before_the_run_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[int] = []

    def handler(number: int, frame: FrameType | None) -> None:
        _ = frame
        received.append(number)

    @command("serve")
    def serve() -> None:
        raise_if_handled(signal.SIGTERM)

    _ = signal.signal(signal.SIGTERM, handler)
    exit_ = call(serve, monkeypatch)

    assert (exit_.code, received) == (0, [signal.SIGTERM])
    assert signal.getsignal(signal.SIGTERM) is handler


def test_an_ignored_sigterm_stays_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    during: list[object] = []

    @command("probe")
    def probe() -> None:
        during.append(signal.getsignal(signal.SIGTERM))

    _ = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    exit_ = call(probe, monkeypatch)

    assert (exit_.code, during) == (0, [signal.SIG_IGN])
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN


def test_testing_run_changes_no_handler_or_excepthook() -> None:
    excepthook = sys.excepthook
    during: list[object] = []

    @command("probe")
    def probe() -> None:
        during.extend([signal.getsignal(signal.SIGTERM), sys.excepthook])

    result = run(probe, [])

    assert result.returncode == 0
    assert during == [signal.SIG_DFL, excepthook]


def test_missing_or_closed_output_streams_are_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = io.StringIO()
    closed.close()

    @command("quiet")
    def quiet() -> None:
        pass

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", closed)
    exit_ = call(quiet, monkeypatch)
    monkeypatch.undo()

    assert exit_.code == 0


class Writer:
    def __init__(self) -> None:
        self.flushes: int = 0

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        self.flushes += 1


def test_an_output_stream_without_closed_is_flushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = Writer()

    @command("quiet")
    def quiet() -> None:
        pass

    monkeypatch.setattr(sys, "stdout", stdout)
    exit_ = call(quiet, monkeypatch)
    monkeypatch.undo()

    assert (exit_.code, stdout.flushes) == (0, 1)


@POSIX
@pytest.mark.parametrize("lines", [1, 100000])
def test_a_closed_stdout_pipe_ends_quietly_with_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lines: int
) -> None:
    log = tmp_path / "stderr.txt"

    @command("many")
    def many() -> str:
        return "line\n" * lines

    with broken_pipe() as stdout, log.open("w", encoding="utf-8") as stderr:
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)
        exit_ = call(many, monkeypatch)
        monkeypatch.undo()
        print("later", file=stderr)

    assert exit_.code == 1
    assert log.read_text(encoding="utf-8") == "later\n"


@POSIX
def test_a_closed_stderr_pipe_ends_with_1_and_keeps_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "stdout.txt"

    @command("report")
    def report() -> None:
        _ = sys.stdout.write("important result\n")
        _ = sys.stderr.write("50%")

    with output.open("w", encoding="utf-8") as stdout, broken_pipe() as stderr:
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)
        exit_ = call(report, monkeypatch)
        monkeypatch.undo()
        print("later", file=stdout)

    assert exit_.code == 1
    assert output.read_text(encoding="utf-8") == "important result\nlater\n"


def test_a_broken_pipe_that_is_not_the_output_shows_its_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @command("feed")
    def feed() -> None:
        raise BrokenPipeError

    with (
        (tmp_path / "stdout.txt").open("w", encoding="utf-8") as stdout,
        (tmp_path / "stderr.txt").open("w", encoding="utf-8") as stderr,
    ):
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)
        monkeypatch.setattr(sys, "argv", ["feed"])
        with pytest.raises(BrokenPipeError):
            _ = feed()


@POSIX
def test_without_poll_a_closed_pipe_is_left_to_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @command("many")
    def many() -> str:
        return "line\n" * 100000

    monkeypatch.delattr(select, "poll")
    with broken_pipe() as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "argv", ["many"])
        with pytest.raises(BrokenPipeError):
            _ = many()
        monkeypatch.undo()


@POSIX
@pytest.mark.parametrize(
    ("number", "returncode"), [(signal.SIGINT, -signal.SIGINT), (signal.SIGTERM, 143)]
)
def test_a_real_process_stops_cleanly_on_a_signal(
    tmp_path: Path, number: signal.Signals, returncode: int
) -> None:
    skip_if_ignored(number)
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


@POSIX
@pytest.mark.parametrize(
    ("number", "returncode"), [(signal.SIGINT, -signal.SIGINT), (signal.SIGTERM, 143)]
)
def test_a_real_process_whose_reader_is_gone_stops_quietly_on_a_signal(
    tmp_path: Path, number: signal.Signals, returncode: int
) -> None:
    skip_if_ignored(number)
    script = tmp_path / "pending.py"
    _ = script.write_text(PENDING, encoding="utf-8")
    with subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout is not None
            assert process.stderr is not None
            assert process.stdout.readline() == "ready\n"
            process.stdout.close()
            process.send_signal(number)
            stderr = cast("str", process.stderr.read())
            _ = process.wait(timeout=10)
        finally:
            process.kill()

    assert (process.returncode, stderr) == (returncode, "")


@POSIX
def test_a_real_process_shows_the_traceback_of_a_bug(tmp_path: Path) -> None:
    script = tmp_path / "serve.py"
    _ = script.write_text(SERVE, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script), "--crash"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert result.stdout == "ready\ncleaned up\n"
    assert result.stderr.startswith("Traceback (most recent call last):\n")
    assert result.stderr.endswith("ValueError: boom\n")


@POSIX
def test_a_real_process_piped_into_an_early_exit_ends_quietly(tmp_path: Path) -> None:
    script = tmp_path / "many.py"
    _ = script.write_text(MANY, encoding="utf-8")
    with subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        assert process.stdout is not None
        assert process.stderr is not None
        first = cast("str", process.stdout.readline())
        process.stdout.close()
        stderr = cast("str", process.stderr.read())
        returncode = process.wait(timeout=30)

    assert (first, returncode, stderr) == ("0\n", 1, "")


def skip_if_ignored(number: int) -> None:
    if signal.getsignal(number) is signal.SIG_IGN:
        pytest.skip("this process ignores the signal, so its child does too")
