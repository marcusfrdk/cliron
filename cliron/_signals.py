import contextlib
import os
import select
import signal
import sys
import threading
import typing
from collections.abc import Callable, Coroutine, Generator
from types import FrameType, TracebackType
from typing import NoReturn

ExceptHook = Callable[
    [type[BaseException], BaseException, TracebackType | None], object
]

TERMINATED = 128 + signal.SIGTERM


def finish(run: Callable[[], int]) -> NoReturn:
    if threading.current_thread() is not threading.main_thread():
        raise SystemExit(run())
    try:
        with _terminate_on_signals():
            code = run()
            _flush()
    except BrokenPipeError:
        if not _silence_closed_output():
            raise
        code = 1
    except BaseException as error:
        _ = _silence_closed_output()
        if isinstance(error, KeyboardInterrupt):
            sys.excepthook = _without_traceback_for(error, sys.excepthook)
        raise
    raise SystemExit(code)


@contextlib.contextmanager
def _terminate_on_signals() -> Generator[None]:
    numbers = [
        number
        for number in _termination_signals()
        if signal.getsignal(number) is signal.SIG_DFL
    ]
    for number in numbers:
        _ = signal.signal(number, _terminate)
    try:
        yield
    finally:
        for number in numbers:
            _ = signal.signal(number, signal.SIG_DFL)


def run_in_loop(coroutine: Coroutine[object, None, int]) -> int:
    import asyncio

    try:
        _ = asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        coroutine.close()
        message = (
            "cliron runs async functions in an event loop of its own, but one is "
            "already running in this thread. Call the CLI from synchronous code, "
            "such as a test that isn't async."
        )
        raise RuntimeError(message)
    with asyncio.Runner() as runner:
        return runner.run(_cancelled_on_terminate(coroutine))


async def _cancelled_on_terminate(coroutine: Coroutine[object, None, int]) -> int:
    import asyncio

    loop = asyncio.get_running_loop()
    task = typing.cast("asyncio.Task[int]", asyncio.current_task())
    terminated: list[int] = []

    def cancel(number: int, frame: FrameType | None) -> None:
        _ = frame
        terminated.append(number)
        _ = loop.call_soon_threadsafe(task.cancel)

    ours = threading.current_thread() is threading.main_thread()
    numbers = [
        number
        for number in _termination_signals()
        if ours and signal.getsignal(number) is _terminate
    ]
    for number in numbers:
        _ = signal.signal(number, cancel)
    try:
        return await coroutine
    except asyncio.CancelledError:
        if terminated:
            raise SystemExit(TERMINATED) from None
        raise
    finally:
        for number in numbers:
            _ = signal.signal(number, _terminate)


def _termination_signals() -> list[int]:
    numbers: list[int] = [signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        numbers.append(signal.SIGBREAK)
    return numbers


def _terminate(number: int, frame: FrameType | None) -> NoReturn:
    _ = (number, frame)
    raise SystemExit(TERMINATED)


def _without_traceback_for(
    interrupt: KeyboardInterrupt, previous: ExceptHook
) -> ExceptHook:
    def hook(
        kind: type[BaseException], error: BaseException, traceback: TracebackType | None
    ) -> None:
        if error is not interrupt:
            _ = previous(kind, error, traceback)

    return hook


def _flush() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not getattr(stream, "closed", False):
            _ = stream.flush()


def _silence_closed_output() -> bool:
    closed = [
        descriptor
        for descriptor in _output_descriptors()
        if _has_lost_its_reader(descriptor)
    ]
    for descriptor in closed:
        _silence(descriptor)
    return bool(closed)


def _output_descriptors() -> list[int]:
    descriptors: list[int] = []
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError, ValueError):
            descriptors.append(stream.fileno())
    return descriptors


def _has_lost_its_reader(descriptor: int) -> bool:
    if not hasattr(select, "poll"):
        return False
    poller = select.poll()
    poller.register(descriptor, select.POLLOUT)
    return any(
        events & (select.POLLERR | select.POLLHUP) for _, events in poller.poll(0)
    )


def _silence(descriptor: int) -> None:
    devnull = os.open(os.devnull, os.O_WRONLY)
    _ = os.dup2(devnull, descriptor)
    os.close(devnull)
