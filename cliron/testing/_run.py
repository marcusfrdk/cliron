import contextlib
import io
import os
import subprocess
import sys
from collections.abc import Generator, Mapping
from pathlib import Path

from cliron._roots import Command, Group, main


def run(
    cli: Command | Group,
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
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
        keeps the environment as it is.
    :param input: The text to pipe into the CLI. ``None`` pipes nothing, as
        when stdin is the null device.
    :returns: The arguments, the exit code, and everything printed to stdout
        and stderr.
    """
    stdout = _Capture("strict")
    stderr = _Capture("backslashreplace")
    with (
        _environment(env),
        _stdin(input),
        contextlib.redirect_stdout(stdout.stream),
        contextlib.redirect_stderr(stderr.stream),
    ):
        try:
            returncode = main(cli, args)
        except SystemExit as exit_:
            returncode = _exit_code(exit_)
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
def _stdin(text: str | None) -> Generator[None]:
    with (
        Path(os.devnull).open(encoding="utf-8") if text is None else io.StringIO(text)
    ) as stream:
        saved = sys.stdin
        sys.stdin = stream
        try:
            yield
        finally:
            sys.stdin = saved


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
