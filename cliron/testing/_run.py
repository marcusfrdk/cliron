import contextlib
import io
import subprocess
import sys

from cliron._roots import Command, Group, main


def run(cli: Command | Group, args: list[str]) -> subprocess.CompletedProcess[str]:
    """
    Run a CLI in this process, as a test would run it in its own.

    An exception the CLI doesn't handle propagates, so a test fails with its
    traceback. A ``SystemExit`` the CLI raises becomes the exit code.

    :param cli: The command or group to run.
    :param args: The command line after the program's name, one word per item.
    :returns: The arguments, the exit code, and everything printed to stdout
        and stderr.
    """
    stdout = _Capture("strict")
    stderr = _Capture("backslashreplace")
    with (
        contextlib.redirect_stdout(stdout.stream),
        contextlib.redirect_stderr(stderr.stream),
    ):
        try:
            returncode = main(cli, args)
        except SystemExit as exit_:
            returncode = _exit_code(exit_)
    return subprocess.CompletedProcess(args, returncode, stdout.text(), stderr.text())


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
