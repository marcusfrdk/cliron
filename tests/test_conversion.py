import sys
from datetime import date, datetime, time
from enum import Enum, auto
from pathlib import Path
from typing import Literal

import pytest

from cliron import argument, command, option
from cliron.testing import run

SHADE = Enum("Shade", {"DARK": "dark"}, type=str)


class Sort(Enum):
    NAME = auto()
    SIZE = auto()
    MODIFIED_AT = auto()


@pytest.mark.parametrize("word", ["Ada", "", " two words "])
def test_str_argument_is_passed_as_written(word: str) -> None:
    @command("echo")
    @argument("text")
    def echo(text: str) -> str:
        return repr(text)

    result = run(echo, [word])

    assert result.returncode == 0
    assert result.stdout == f"{word!r}\n"
    assert result.stderr == ""


@pytest.mark.parametrize("args", [["--text="], ["--text", ""]])
def test_str_option_accepts_an_empty_value(args: list[str]) -> None:
    @command("echo")
    @option("text")
    def echo(text: str) -> str:
        return repr(text)

    result = run(echo, args)

    assert result.returncode == 0
    assert result.stdout == "''\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("word", "expected"),
    [("3", "3"), ("-5", "-5"), ("+7", "7"), ("007", "7")],
)
def test_int_accepts_ascii_digits_with_an_optional_sign(
    word: str, expected: str
) -> None:
    @command("repeat")
    @option("count")
    def repeat(count: int) -> str:
        return repr(count)

    result = run(repeat, ["--count", word])

    assert result.returncode == 0
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "word", ["two", "1_000", " 1", "1.5", "\N{ARABIC-INDIC DIGIT ONE}", ""]
)
def test_int_rejects_anything_but_ascii_digits_with_an_optional_sign(
    word: str,
) -> None:
    @command("repeat")
    @option("count")
    def repeat(count: int) -> str:
        return repr(count)

    result = run(repeat, ["--count", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --count: {word!r} isn't a whole number.\n"
        "Run 'repeat --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("1.5", "1.5"),
        ("-.5", "-0.5"),
        ("1e3", "1000.0"),
        ("1.", "1.0"),
        ("+2E-3", "0.002"),
    ],
)
def test_float_accepts_ascii_decimals_with_a_sign_point_and_exponent(
    word: str, expected: str
) -> None:
    @command("scale")
    @option("ratio")
    def scale(ratio: float) -> str:
        return repr(ratio)

    result = run(scale, ["--ratio", word])

    assert result.returncode == 0
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "word",
    ["inf", "nan", "1_0", "abc", "", " 1.5", "1.5 ", "\N{ARABIC-INDIC DIGIT ONE}.5"],
)
def test_float_rejects_special_values_underscores_and_words(word: str) -> None:
    @command("scale")
    @option("ratio")
    def scale(ratio: float) -> str:
        return repr(ratio)

    result = run(scale, ["--ratio", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --ratio: {word!r} isn't a number.\nRun 'scale --help' for usage.\n"
    )


def test_path_argument_becomes_a_path() -> None:
    received: list[object] = []

    @command("save")
    @argument("output")
    def save(output: Path) -> None:
        received.append(output)

    result = run(save, ["reports/today.txt"])

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert received == [Path("reports/today.txt")]


@pytest.mark.parametrize("args", [["--output="], ["--output", ""]])
def test_path_rejects_an_empty_value(args: list[str]) -> None:
    received: list[object] = []

    @command("save")
    @option("output")
    def save(output: Path) -> None:
        received.append(output)

    result = run(save, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: --output: a path can't be empty.\nRun 'save --help' for usage.\n"
    )
    assert received == []


def test_date_is_parsed_from_iso_format() -> None:
    @command("log")
    @option("since")
    def log(since: date) -> str:
        return repr(since)

    result = run(log, ["--since", "2026-10-24"])

    assert result.returncode == 0
    assert result.stdout == "datetime.date(2026, 10, 24)\n"
    assert result.stderr == ""


@pytest.mark.parametrize("word", ["2026-13-01", "24 October", ""])
def test_date_rejects_a_value_that_is_not_an_iso_date(word: str) -> None:
    @command("log")
    @option("since")
    def log(since: date) -> str:
        return repr(since)

    result = run(log, ["--since", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --since: {word!r} isn't a date (YYYY-MM-DD).\n"
        "Run 'log --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("2026-10-24 09:30", "datetime.datetime(2026, 10, 24, 9, 30)"),
        ("2026-10-24T09:30:15", "datetime.datetime(2026, 10, 24, 9, 30, 15)"),
        ("2026-10-24", "datetime.datetime(2026, 10, 24, 0, 0)"),
    ],
)
def test_datetime_is_parsed_from_iso_format(word: str, expected: str) -> None:
    @command("remind")
    @option("at")
    def remind(at: datetime) -> str:
        return repr(at)

    result = run(remind, ["--at", word])

    assert result.returncode == 0
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


@pytest.mark.parametrize("word", ["2026-10-24 25:00", "tomorrow", ""])
def test_datetime_rejects_a_value_that_is_not_an_iso_datetime(word: str) -> None:
    @command("remind")
    @option("at")
    def remind(at: datetime) -> str:
        return repr(at)

    result = run(remind, ["--at", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --at: {word!r} isn't a date and time (YYYY-MM-DD HH:MM).\n"
        "Run 'remind --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("word", "expected"),
    [("09:30", "datetime.time(9, 30)"), ("23:59:59", "datetime.time(23, 59, 59)")],
)
def test_time_is_parsed_from_iso_format(word: str, expected: str) -> None:
    @command("alarm")
    @option("wake")
    def alarm(wake: time) -> str:
        return repr(wake)

    result = run(alarm, ["--wake", word])

    assert result.returncode == 0
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


@pytest.mark.parametrize("word", ["25:00", "noon", ""])
def test_time_rejects_a_value_that_is_not_an_iso_time(word: str) -> None:
    @command("alarm")
    @option("wake")
    def alarm(wake: time) -> str:
        return repr(wake)

    result = run(alarm, ["--wake", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --wake: {word!r} isn't a time (HH:MM or HH:MM:SS).\n"
        "Run 'alarm --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("word", "expected"),
    [("name", Sort.NAME), ("size", Sort.SIZE), ("modified-at", Sort.MODIFIED_AT)],
)
def test_enum_member_is_chosen_by_its_lowercase_kebab_case_name(
    word: str, expected: Sort
) -> None:
    received: list[object] = []

    @command("list_files")
    @option("sort")
    def list_files(sort: Sort) -> None:
        received.append(sort)

    result = run(list_files, ["--sort", word])

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert received == [expected]


@pytest.mark.parametrize("word", ["MODIFIED_AT", "modified_at", "Name", "3", ""])
def test_enum_rejects_other_spellings_and_lists_the_choices(word: str) -> None:
    received: list[object] = []

    @command("list_files")
    @option("sort")
    def list_files(sort: Sort) -> None:
        received.append(sort)

    result = run(list_files, ["--sort", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --sort: {word!r} isn't one of name, size, modified-at.\n"
        "Run 'list-files --help' for usage.\n"
    )
    assert received == []


@pytest.mark.parametrize("word", ["plain", "fancy"])
def test_literal_accepts_each_of_its_strings(word: str) -> None:
    @command("render")
    @option("style")
    def render(style: Literal["plain", "fancy"]) -> str:
        return repr(style)

    result = run(render, ["--style", word])

    assert result.returncode == 0
    assert result.stdout == f"{word!r}\n"
    assert result.stderr == ""


@pytest.mark.parametrize("word", ["Plain", "fancy ", "plai", ""])
def test_literal_rejects_anything_but_its_exact_strings(word: str) -> None:
    @command("render")
    @option("style")
    def render(style: Literal["plain", "fancy"]) -> str:
        return repr(style)

    result = run(render, ["--style", word])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: --style: {word!r} isn't one of plain, fancy.\n"
        "Run 'render --help' for usage.\n"
    )


@pytest.mark.parametrize(("args", "expected"), [([], "None"), (["--limit", "3"], "3")])
def test_union_with_none_converts_to_the_inner_type(
    args: list[str], expected: str
) -> None:
    @command("search")
    @option("limit")
    def search(limit: int | None = None) -> str:
        return repr(limit)

    result = run(search, args)

    assert result.returncode == 0
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("args", "expected"), [([], "None"), (["--style", "plain"], "'plain'")]
)
def test_typing_optional_written_as_literal_or_none_converts_to_the_literal(
    args: list[str], expected: str
) -> None:
    @command("render")
    @option("style")
    def render(style: Literal["plain", "fancy"] | None = None) -> str:
        return repr(style)

    result = run(render, args)

    assert result.returncode == 0
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


def test_union_with_none_reports_a_conversion_error_of_the_inner_type() -> None:
    @command("search")
    @option("limit")
    def search(limit: int | None = None) -> str:
        return repr(limit)

    result = run(search, ["--limit", "two"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: --limit: 'two' isn't a whole number.\nRun 'search --help' for usage.\n"
    )


def test_union_with_none_without_a_default_is_required() -> None:
    @command("search")
    @option("limit")
    def search(limit: int | None) -> str:
        return repr(limit)

    result = run(search, [])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: --limit is required.\nRun 'search --help' for usage.\n"
    )


def test_list_option_collects_every_occurrence_in_order() -> None:
    @command("tag")
    @option("label", "-l")
    def tag(label: list[str]) -> str:
        return repr(label)

    result = run(tag, ["--label", "b", "-l", "a", "--label=c", "-lb"])

    assert result.returncode == 0
    assert result.stdout == "['b', 'a', 'c', 'b']\n"
    assert result.stderr == ""


def test_tuple_option_collects_every_occurrence_in_order_as_a_tuple() -> None:
    @command("resize")
    @option("width", "-w")
    def resize(width: tuple[int, ...]) -> str:
        return repr(width)

    result = run(resize, ["-w", "30", "--width", "10", "-w20", "--width=-5"])

    assert result.returncode == 0
    assert result.stdout == "(30, 10, 20, -5)\n"
    assert result.stderr == ""


def test_list_argument_takes_the_remaining_words_in_order() -> None:
    @command("total")
    @argument("label")
    @argument("numbers")
    def total(label: str, numbers: list[int]) -> str:
        return repr((label, numbers))

    result = run(total, ["sum", "3", "-1", "2"])

    assert result.returncode == 0
    assert result.stdout == "('sum', [3, -1, 2])\n"
    assert result.stderr == ""


def test_tuple_argument_takes_the_remaining_words_as_a_tuple() -> None:
    @command("total")
    @argument("numbers")
    def total(numbers: tuple[float, ...]) -> str:
        return repr(numbers)

    result = run(total, ["1.5", "2", "-.5"])

    assert result.returncode == 0
    assert result.stdout == "(1.5, 2.0, -0.5)\n"
    assert result.stderr == ""


def test_inputs_that_are_not_given_take_their_defaults() -> None:
    @command("greet")
    @argument("name")
    @option("count")
    @option("sort")
    def greet(name: str = "world", count: int = 1, sort: Sort = Sort.SIZE) -> str:
        return repr((name, count, sort))

    result = run(greet, [])

    assert result.returncode == 0
    assert result.stdout == "('world', 1, <Sort.SIZE: 2>)\n"
    assert result.stderr == ""


def test_empty_tuple_default_is_used_when_no_value_is_given() -> None:
    @command("lint")
    @argument("files")
    @option("exclude")
    def lint(files: tuple[str, ...] = (), exclude: tuple[str, ...] = ()) -> str:
        return repr((files, exclude))

    result = run(lint, [])

    assert result.returncode == 0
    assert result.stdout == "((), ())\n"
    assert result.stderr == ""


def test_list_option_without_a_default_is_required() -> None:
    @command("tag")
    @option("label")
    def tag(label: list[str]) -> str:
        return repr(label)

    result = run(tag, [])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: --label is required.\nRun 'tag --help' for usage.\n"
    )


def test_list_argument_without_a_default_is_required() -> None:
    @command("lint")
    @argument("files")
    def lint(files: list[Path]) -> str:
        return repr(len(files))

    result = run(lint, [])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: FILES is required.\nRun 'lint --help' for usage.\n"
    )


def test_list_option_reports_one_error_per_invalid_value() -> None:
    @command("resize")
    @option("width", "-w")
    def resize(width: list[int]) -> str:
        return repr(width)

    result = run(resize, ["-w", "1", "-w", "x", "-w", "2", "-w", "y"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: --width: 'x' isn't a whole number.\n"
        "error: --width: 'y' isn't a whole number.\n"
        "Run 'resize --help' for usage.\n"
    )


def test_list_argument_reports_one_error_per_invalid_value() -> None:
    @command("total")
    @argument("numbers")
    def total(numbers: list[int]) -> str:
        return repr(numbers)

    result = run(total, ["1", "x", "2", "y"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: NUMBERS: 'x' isn't a whole number.\n"
        "error: NUMBERS: 'y' isn't a whole number.\n"
        "Run 'total --help' for usage.\n"
    )


def test_command_receives_instances_of_the_annotated_types() -> None:
    @command("report")
    @argument("count")
    @option("ratio")
    @option("output")
    @option("since")
    @option("sort")
    def report(count: int, ratio: float, output: Path, since: date, sort: Sort) -> str:
        checks: dict[str, tuple[object, type[object]]] = {
            "count": (count, int),
            "ratio": (ratio, float),
            "output": (output, Path),
            "since": (since, date),
            "sort": (sort, Sort),
        }
        return ", ".join(
            f"{name} is {kind.__name__}"
            for name, (value, kind) in checks.items()
            if isinstance(value, kind)
        )

    args = ["3", "--ratio", "2", "--output", "out.txt"]
    result = run(report, [*args, "--since", "2026-10-24", "--sort", "size"])

    assert result.returncode == 0
    assert result.stdout == (
        "count is int, ratio is float, output is Path, since is date, sort is Sort\n"
    )
    assert result.stderr == ""


def test_int_with_more_digits_than_python_allows_is_rejected() -> None:
    @command("count")
    @option("number")
    def count(number: int = 0) -> str:
        return str(number)

    limit = sys.get_int_max_str_digits()
    result = run(count, ["--number", "1" * (limit + 1)])

    assert result.returncode == 2
    assert result.stderr == (
        f"error: --number: a whole number can't have more than {limit} digits.\n"
        "Run 'count --help' for usage.\n"
    )


@pytest.mark.parametrize("word", ["1e999", "-1e400"])
def test_float_that_overflows_is_out_of_range(word: str) -> None:
    @command("ratio")
    @option("value")
    def ratio(value: float = 0.0) -> str:
        return repr(value)

    result = run(ratio, [f"--value={word}"])

    assert result.returncode == 2
    assert result.stderr == (
        f"error: --value: {word!r} is out of range.\nRun 'ratio --help' for usage.\n"
    )


def test_literal_of_a_str_enum_member_is_typed_as_its_value() -> None:
    def paint(shade: str | None = None) -> str:
        return repr(shade)

    paint.__annotations__["shade"] = 'Literal[SHADE["DARK"]] | None'
    cli = command("paint")(option("shade")(paint))

    result = run(cli, ["--shade", "dark"])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "<Shade.DARK: 'dark'>\n",
        "",
    )
