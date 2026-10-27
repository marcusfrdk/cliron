import contextlib
import sys
import time
import typing
from collections.abc import Generator, Mapping
from typing import final

Clock = tuple[int, int]

_TIME_UNITS = {"ns": 1, "us": 10**3, "µs": 10**3, "ms": 10**6, "s": 10**9}
_MEMORY_UNITS = {"b": 1, "kb": 10**3, "mb": 10**6, "gb": 10**9}
_SHOWN = {"us": "µs", "b": "B", "kb": "kB", "mb": "MB", "gb": "GB"}


def imported() -> Clock:
    return typing.cast("Clock", vars(sys.modules["cliron"])["_IMPORTED"])


def now() -> Clock:
    return time.perf_counter_ns(), time.process_time_ns()


@contextlib.contextmanager
def measured(environ: Mapping[str, str], started: Clock) -> Generator[None]:
    try:
        yield
    finally:
        lines = _lines(environ, started)
        if lines:
            with contextlib.suppress(OSError, ValueError):
                _ = sys.stdout.flush()
            _ = sys.stderr.write("".join(f"{line}\n" for line in lines))


def _lines(environ: Mapping[str, str], started: Clock) -> list[str]:
    ended = now()
    lines: list[str] = []
    for name, label, spent in [
        ("CLIRON_TIME", "time", ended[0] - started[0]),
        ("CLIRON_CPU", "cpu", ended[1] - started[1]),
    ]:
        unit = _unit(environ.get(name), _TIME_UNITS, "ms")
        if unit is not None:
            lines.append(f"{label}: {_amount(spent, unit, _TIME_UNITS)}")
    unit = _unit(environ.get("CLIRON_MEMORY"), _MEMORY_UNITS, "mb")
    if unit is not None:
        lines.append(f"memory: {_amount(_peak_memory(), unit, _MEMORY_UNITS)} peak")
    return lines


def _unit(value: str | None, units: Mapping[str, int], default: str) -> str | None:
    if value in {None, "", "0"}:
        return None
    unit = str(value).lower()
    return unit if unit in units else default


def _amount(count: int, unit: str, units: Mapping[str, int]) -> str:
    scale = units[unit]
    number = str(count) if scale == 1 else f"{count / scale:.3f}"
    return f"{number} {_SHOWN.get(unit, unit)}"


def _peak_memory() -> int:
    if sys.platform == "win32":
        return _windows_peak_memory()
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def _windows_peak_memory() -> int:
    import ctypes

    @final
    class Counters(ctypes.Structure):
        _fields_ = (
            ("cb", ctypes.c_uint32),
            ("page_fault_count", ctypes.c_uint32),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        )

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.K32GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(Counters),
        ctypes.c_uint32,
    )
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    process = typing.cast("int", kernel32.GetCurrentProcess())
    _ = typing.cast(
        "int",
        kernel32.K32GetProcessMemoryInfo(
            process, ctypes.pointer(counters), counters.cb
        ),
    )
    return typing.cast("int", counters.peak_working_set_size)
