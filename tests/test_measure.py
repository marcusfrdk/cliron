import ctypes
import operator
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

from cliron import command, env
from cliron.testing import run

PEAK = 41234432

MILLISECONDS = r"\d+\.\d{3} ms"

SCRIPT = """
import time

from cliron import command

time.sleep(0.05)


@command("hello")
def hello() -> str:
    {body}


hello()
"""


@command("hello")
def hello() -> str:
    return "hello"


class Function:
    def __init__(self, call: Callable[..., int]) -> None:
        self.call: Callable[..., int] = call
        self.restype: object = None
        self.argtypes: object = None

    def __call__(self, *args: object) -> int:
        return self.call(*args)


def fill(process: object, counters: object, size: int) -> int:
    _ = (process, size)
    structure = cast("ctypes.Structure", operator.attrgetter("contents")(counters))
    structure.peak_working_set_size = PEAK
    return 1


class Kernel32:
    def __init__(self, name: str) -> None:
        _ = name
        self.GetCurrentProcess: Function = Function(lambda: -1)
        self.K32GetProcessMemoryInfo: Function = Function(fill)


def resource_module(peak: int) -> ModuleType:
    def getrusage(who: int) -> SimpleNamespace:
        return SimpleNamespace(ru_maxrss=peak, who=who)

    module = ModuleType("resource")
    vars(module).update(RUSAGE_SELF=0, getrusage=getrusage)
    return module


@pytest.mark.parametrize(
    ("variable", "label"), [("CLIRON_TIME", "time"), ("CLIRON_CPU", "cpu")]
)
@pytest.mark.parametrize(
    ("value", "amount"),
    [
        ("ns", r"\d+ ns"),
        ("us", r"\d+\.\d{3} µs"),
        ("µs", r"\d+\.\d{3} µs"),
        ("ms", MILLISECONDS),
        ("s", r"\d+\.\d{3} s"),
        ("MS", MILLISECONDS),
        ("1", MILLISECONDS),
        ("true", MILLISECONDS),
        ("sm", MILLISECONDS),
    ],
)
def test_time_and_cpu_use_the_unit_the_value_names(
    variable: str, label: str, value: str, amount: str
) -> None:
    result = run(hello, [], env={variable: value})

    assert result.stdout == "hello\n"
    assert re.fullmatch(rf"{label}: {amount}\n", result.stderr)


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("b", f"{PEAK} B"),
        ("kb", "41234.432 kB"),
        ("MB", "41.234 MB"),
        ("gb", "0.041 GB"),
        ("1", "41.234 MB"),
    ],
)
@pytest.mark.parametrize(
    ("platform", "peak"), [("darwin", PEAK), ("linux", PEAK // 1024)]
)
def test_memory_uses_the_unit_the_value_names(
    monkeypatch: pytest.MonkeyPatch, platform: str, peak: int, value: str, shown: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setitem(sys.modules, "resource", resource_module(peak))

    result = run(hello, [], env={"CLIRON_MEMORY": value})

    assert result.stderr == f"memory: {shown} peak\n"


def test_windows_memory_is_the_peak_working_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", Kernel32, raising=False)

    result = run(hello, [], env={"CLIRON_MEMORY": "b"})

    assert result.stderr == f"memory: {PEAK} B peak\n"


def test_memory_is_read_on_this_platform() -> None:
    result = run(hello, [], env={"CLIRON_MEMORY": "1"})

    assert re.fullmatch(r"memory: \d+\.\d{3} MB peak\n", result.stderr)


@pytest.mark.parametrize("value", ["", "0"])
def test_an_empty_value_or_0_turns_a_variable_off(value: str) -> None:
    variables = {"CLIRON_TIME": value, "CLIRON_CPU": value, "CLIRON_MEMORY": value}

    assert run(hello, [], env=variables).stderr == ""


def test_the_lines_come_last_and_in_order() -> None:
    variables = {"CLIRON_MEMORY": "1", "CLIRON_CPU": "1", "CLIRON_TIME": "1"}

    lines = run(hello, ["--nope"], env=variables).stderr.splitlines()

    assert lines[0] == "error: unknown option '--nope'."
    assert [line.split(":")[0] for line in lines[-3:]] == ["time", "cpu", "memory"]


def test_run_ignores_the_variables_of_the_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLIRON_TIME", "1")

    assert run(hello, []).stderr == ""


def test_a_cli_can_read_the_variables_too() -> None:
    @command("show")
    @env("cliron_time")
    def show(cliron_time: str = "") -> str:
        return f"CLIRON_TIME is {cliron_time!r}"

    result = run(show, [], env={"CLIRON_TIME": "1"})

    assert result.stdout == "CLIRON_TIME is '1'\n"
    assert re.fullmatch(rf"time: {MILLISECONDS}\n", result.stderr)


@pytest.mark.parametrize(
    ("body", "stdout", "stderr"),
    [
        ('return "hello"', "hello\n", rf"time: (?P<ms>{MILLISECONDS})\n"),
        ("raise KeyboardInterrupt", "", rf"time: (?P<ms>{MILLISECONDS})\n"),
        (
            'raise RuntimeError("broken")',
            "",
            rf"time: (?P<ms>{MILLISECONDS})\nTraceback .*RuntimeError: broken\n",
        ),
    ],
)
def test_a_program_counts_from_when_cliron_was_imported(
    tmp_path: Path, body: str, stdout: str, stderr: str
) -> None:
    script = tmp_path / "hello.py"
    _ = script.write_text(SCRIPT.format(body=body), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script)],
        env={
            **{
                name: value
                for name, value in os.environ.items()
                if not name.startswith("CLIRON_")
            },
            "CLIRON_TIME": "ms",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.stdout == stdout
    match = re.fullmatch(stderr, result.stderr, re.DOTALL)
    assert match is not None
    assert float(match["ms"].removesuffix(" ms")) >= 50
