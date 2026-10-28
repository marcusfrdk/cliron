import contextlib
import io
import os
import subprocess
import sys
from collections.abc import Generator, Mapping
from pathlib import Path
from typing import TextIO

from cliron._measure import measured, now
from cliron._parsing import MistakeError
from cliron._roots import Command, Group, main


def run(
    cli: Command | Group,
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
    terminal: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Run a CLI in this process, as a test would run it in its own.

    An exception the CLI doesn't handle propagates, so a test fails with its
    traceback. A ``SystemExit`` the CLI raises becomes the exit code.

    :param cli: The command or group to run.
    :param args: The command line after the program's name, one word per item.
    :param env: The environment variables to run with, in place of this
        process's own, as ``subprocess.run`` takes them. They replace
        ``os.environ`` during the run, which is restored afterwards. ``None``
        keeps the environment as it is. ``CLIRON_TIME``, ``CLIRON_CPU`` and
        ``CLIRON_MEMORY`` count only when they're given here, so a shell's
        don't change a test's output, and the time and CPU time count from the
        start of the run.
    :param input: The text to pipe into the CLI. ``None`` pipes nothing, as
        when stdin is the null device.
    :param terminal: Whether stdin is a terminal instead of a pipe, so that
        ``@fallback(prompt=...)`` asks and reads its answers from ``input``,
        one line each, and ``@stdin`` sees nothing piped.
    :returns: The arguments, the exit code, and everything printed to stdout
        and stderr.
    """
    stdout = _Capture("strict")
    stderr = _Capture("backslashreplace")
    with (
        _environment(env),
        _stdin(input, terminal=terminal),
        contextlib.redirect_stdout(stdout.stream),
        contextlib.redirect_stderr(stderr.stream),
        measured(env or {}, now()),
    ):
        try:
            returncode = main(cli, args)
        except SystemExit as exit_:
            returncode = _exit_code(exit_)
        except MistakeError as mistake:
            raise mistake.error from None
    return subprocess.CompletedProcess(args, returncode, stdout.text(), stderr.text())


@contextlib.contextmanager
def _environment(env: Mapping[str, str] | None) -> Generator[None]:
    if env is None:
        yield
        return
    saved = dict(os.environ)
    os.environ.clear()
    try:
        os.environ.update(env)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@contextlib.contextmanager
def _stdin(text: str | None, *, terminal: bool) -> Generator[None]:
    with _stdin_stream(text, terminal=terminal) as stream:
        saved = sys.stdin
        sys.stdin = stream
        try:
            yield
        finally:
            sys.stdin = saved


def _stdin_stream(text: str | None, *, terminal: bool) -> TextIO:
    if terminal:
        return _Terminal(text or "")
    if text is None:
        return Path(os.devnull).open(encoding="utf-8")
    return io.StringIO(text)


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class _Capture:
    def __init__(self, errors: str) -> None:
        self.buffer: io.BytesIO = io.BytesIO()
        self.stream: io.TextIOWrapper = io.TextIOWrapper(
            self.buffer,
            encoding="utf-8",
            errors=errors,
            newline="",
            write_through=True,
        )

    def text(self) -> str:
        return self.buffer.getvalue().decode(errors="surrogateescape")


def _exit_code(exit_: SystemExit) -> int:
    if exit_.code is None:
        return 0
    if isinstance(exit_.code, int):
        return exit_.code
    _ = sys.stderr.write(f"{exit_.code}\n")
    return 1
