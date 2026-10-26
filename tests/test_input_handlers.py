import re
from collections.abc import Callable
from pathlib import Path

import pytest

from cliron import (
    Context,
    Parent,
    argument,
    between,
    child,
    command,
    env,
    file,
    hook,
    on,
    option,
)
from cliron.testing import run, validate

WIDTH = 80
FALLBACK = Path("fallback.txt")


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def terminal_width(exc: LookupError | ValueError) -> int:
    _ = exc
    return WIDTH


def at_most_ten(exc: ValueError) -> int:
    _ = exc
    return 10


def as_text(exc: ValueError) -> object:
    return str(exc)


def again(exc: ValueError) -> int:
    raise exc


def explain(exc: ValueError) -> int:
    message = f"{exc} Pick 1 to 10."
    raise ValueError(message) from exc


@child
def unchanged(value: Path) -> Path:
    return value


class Keyring(Parent):
    def load(self) -> str | None:
        message = "the keyring is locked"
        raise PermissionError(message)


def anonymous(exc: PermissionError) -> str:
    _ = exc
    return "anonymous"


def use_fallback(exc: ValueError) -> Path:
    _ = exc
    return FALLBACK


@command("show")
@env("columns")
@hook(on.error(), terminal_width)
def show(columns: int) -> int:
    return columns


@pytest.mark.parametrize(
    ("variables", "width"),
    [({}, "80"), ({"COLUMNS": "wide"}, "80"), ({"COLUMNS": "120"}, "120")],
    ids=["missing", "invalid", "given"],
)
def test_a_parents_handler_gives_the_value_when_reading_fails(
    variables: dict[str, str], width: str
) -> None:
    assert run(show, [], env=variables).stdout == f"{width}\n"


def test_a_childs_handler_replaces_the_value_and_the_chain_goes_on() -> None:
    @command("retry")
    @option("retries")
    @between(1, 10)
    @hook(on.error(), at_most_ten)
    @between(1, 5)
    def retry(retries: int = 3) -> int:
        return retries

    assert run(retry, ["--retries", "4"]).stdout == "4\n"
    assert run(retry, ["--retries", "20"]).stderr == (
        "error: --retries: 10 isn't between 1 and 5.\nRun 'retry --help' for usage.\n"
    )


def test_a_childs_handler_runs_for_each_item() -> None:
    @command("pick")
    @argument("numbers")
    @between(1, 10)
    @hook(on.error(), at_most_ten)
    def pick(numbers: list[int]) -> list[int]:
        return numbers

    assert run(pick, ["3", "30", "300"]).stdout == "[\n  3,\n  10,\n  10\n]\n"


def test_a_parents_handler_covers_what_its_children_didnt_handle() -> None:
    @command("retry")
    @option("retries")
    @hook(on.error(), at_most_ten)
    @between(1, 10)
    def retry(retries: int = 3) -> int:
        return retries

    assert run(retry, ["--retries", "20"]).stdout == "10\n"


def test_a_parents_handler_runs_once_for_a_list_and_replaces_it() -> None:
    seen: list[str] = []

    def none_of_them(exc: ValueError) -> list[int]:
        seen.append(str(exc))
        return []

    @command("pick")
    @argument("numbers")
    @hook(on.error(), none_of_them)
    def pick(numbers: list[int]) -> int:
        return len(numbers)

    assert run(pick, ["1", "x", "y"]).stdout == "0\n"
    assert seen == ["NUMBERS: 'x' isn't a whole number."]


def test_a_parents_handler_doesnt_cover_typing_mistakes() -> None:
    @command("retry")
    @option("retries")
    @hook(on.error(), at_most_ten)
    def retry(retries: int = 3) -> int:
        return retries

    assert run(retry, ["--retries"]).stderr == (
        "error: --retries needs a value.\nRun 'retry --help' for usage.\n"
    )


def test_a_handler_that_raises_reports_the_error_as_invalid_input() -> None:
    @command("retry")
    @option("retries")
    @hook(on.error(), again)
    @option("delay")
    @hook(on.error(), explain)
    def retry(retries: int = 3, delay: int = 1) -> int:
        return retries + delay

    result = run(retry, ["--retries", "x", "--delay", "y"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: --retries: 'x' isn't a whole number.\n"
        "error: --delay: 'y' isn't a whole number. Pick 1 to 10.\n"
        "Run 'retry --help' for usage.\n"
    )


def test_a_parents_handler_covers_its_load() -> None:
    @command("whoami")
    @Keyring("user")
    @hook(on.error(), anonymous)
    def whoami(user: str) -> str:
        return user

    @command("strict")
    @Keyring("user")
    def strict(user: str) -> str:
        return user

    assert run(whoami, []).stdout == "anonymous\n"
    with pytest.raises(PermissionError, match="the keyring is locked"):
        _ = run(strict, [])


def test_a_handler_covers_a_default_checked_on_each_run(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    def read(config: Path = missing) -> str:
        return config.name

    def check(config: Path = missing) -> str:
        return config.name

    on_parent = command("read")(
        option("config")(hook(on.error(), use_fallback)(file()(read)))
    )
    on_child = command("check")(
        option("config")(unchanged()(file()(hook(on.error(), use_fallback)(check))))
    )

    assert run(on_parent, []).stdout == "fallback.txt\n"
    assert run(on_child, []).stdout == "missing.txt\n"


def test_a_parents_handler_must_return_the_parameters_type() -> None:
    def text_width(exc: LookupError) -> object:
        return str(exc)

    @command("show")
    @env("columns")
    @hook(on.error(), text_width)
    def show(columns: int) -> int:
        return columns

    message = (
        "hook function 'text_width' returned str, but parameter 'columns' has the "
        "type int. Make it return int."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(show, [], env={})


def test_a_childs_handler_must_return_the_parameters_type() -> None:
    @command("retry")
    @option("retries")
    @between(1, 10)
    @hook(on.error(), as_text)
    def retry(retries: int = 3) -> int:
        return retries

    message = (
        "hook function 'as_text' returned str, but parameter 'retries' has the "
        "type int. Make it return int."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(retry, ["--retries", "20"])


def wants_the_context(exc: ValueError, ctx: Context) -> int:
    _ = (exc, ctx)
    return 1


@pytest.mark.parametrize("attach", [hook])
def test_a_handler_on_a_parent_receives_only_the_exception(
    attach: Callable[..., Callable[[Callable[..., object]], Callable[..., object]]],
) -> None:
    def retry(retries: int = 3) -> int:
        return retries

    cli = command("retry")(
        option("retries")(attach(on.error(), wants_the_context)(retry))
    )

    message = (
        "hook function 'wants_the_context' takes parameter 'ctx', but a handler on a "
        "parent or child receives only the exception, because it runs while the "
        "inputs are read. Remove it."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        validate(cli)
