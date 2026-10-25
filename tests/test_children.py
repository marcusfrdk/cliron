import re
from collections.abc import Callable
from datetime import date, datetime, time
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Literal

import pytest

from cliron import (
    argument,
    between,
    choices,
    command,
    env,
    flag,
    length,
    matches,
    option,
    stdin,
)
from cliron.testing import run, validate

Check = Callable[..., object]

CHECKS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)

START = date(2020, 1, 1)
END = date(2030, 12, 31)


class Color(Enum):
    RED = "red"
    DARK_RED = "dark red"
    BLUE = "blue"


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@command("pick")
@option("keep", "-k")
@between(1, 100)
@option("workers", "-w")
@between(low=1)
@option("percent")
@between(high=100)
@option("ratio")
@between(0, 1)
def pick(
    keep: int = 10, workers: int = 4, percent: int = 50, ratio: float = 0.5
) -> str:
    return f"{keep} {workers} {percent} {ratio}"


@command("name")
@option("user")
@length(3, 20)
@option("phrase")
@length(low=12)
@option("title")
@length(high=5)
@option("nickname")
@length(low=1)
def name(
    user: str = "ada",
    phrase: str = "correct horse",
    title: str = "Dr",
    nickname: str = "a",
) -> str:
    return f"{user} {phrase} {title} {nickname}"


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["-k", "1", "-w", "1", "--percent", "100", "--ratio", "1"], None),
        (["-k", "0"], "--keep: 0 isn't between 1 and 100."),
        (["-k", "101"], "--keep: 101 isn't between 1 and 100."),
        (["-w", "0"], "--workers: 0 is less than 1."),
        (["--percent", "101"], "--percent: 101 is more than 100."),
        (["--ratio", "1.5"], "--ratio: 1.5 isn't between 0 and 1."),
    ],
)
def test_between(args: list[str], error: str | None) -> None:
    result = run(pick, args)

    assert result.stderr == (
        "" if error is None else f"error: {error}\nRun 'pick --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--user", "bob", "--nickname", "b"], None),
        (["--user", "ab"], "--user: 'ab' isn't between 3 and 20 characters long."),
        (
            ["--phrase", "secret"],
            "--phrase: 'secret' is shorter than 12 characters.",
        ),
        (["--title", "Professor"], "--title: 'Professor' is longer than 5 characters."),
        (["--nickname="], "--nickname: '' is shorter than 1 character."),
    ],
)
def test_length(args: list[str], error: str | None) -> None:
    result = run(name, args)

    assert result.stderr == (
        "" if error is None else f"error: {error}\nRun 'name --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("value", "valid"),
    [("summer-2026", True), ("Summer", False), ("summer!", False), ("", False)],
)
def test_matches_the_whole_text(*, value: str, valid: bool) -> None:
    @command("tag")
    @option("label")
    @matches(r"[a-z0-9-]+")
    def tag(label: str = "x") -> str:
        return label

    result = run(tag, ["--label", value])

    assert result.returncode == (0 if valid else 2)
    if not valid:
        assert f"--label: {value!r} doesn't match [a-z0-9-]+." in result.stderr


def test_matches_keeps_the_patterns_own_flags() -> None:
    @command("tag")
    @option("label")
    @matches(r"(?i)[a-z]+")
    def tag(label: str = "x") -> str:
        return label

    assert run(tag, ["--label", "ABC"]).stdout == "ABC\n"


CHOICES = {
    "values": (choices("zip", "tar"), "rar", "zip", "'rar' isn't one of zip, tar."),
    "list": (choices(["zip", "tar"]), "rar", "tar", "'rar' isn't one of zip, tar."),
    "tuple": (choices(("zip", "tar")), "rar", "tar", "'rar' isn't one of zip, tar."),
    "set": (choices({"zip", "tar"}), "rar", "tar", "'rar' isn't one of tar, zip."),
    "frozenset": (
        choices(frozenset({"zip", "tar"})),
        "rar",
        "zip",
        "'rar' isn't one of tar, zip.",
    ),
}


@pytest.mark.parametrize("case", CHOICES)
def test_choices_takes_values_or_one_collection(case: str) -> None:
    child, bad, good, error = CHOICES[case]

    @command("pack")
    @option("archive_format")
    @child
    def pack(archive_format: str = "zip") -> str:
        return archive_format

    assert run(pack, ["--archive-format", good]).stdout == f"{good}\n"
    assert run(pack, ["--archive-format", bad]).stderr == (
        f"error: --archive-format: {error}\nRun 'pack --help' for usage.\n"
    )


def test_choices_narrows_an_enum() -> None:
    @command("paint")
    @option("color")
    @choices(Color.RED, Color.DARK_RED)
    def paint(color: Color = Color.RED) -> str:
        return color.name

    assert run(paint, ["--color", "dark-red"]).stdout == "DARK_RED\n"
    assert run(paint, ["--color", "blue"]).stderr == (
        "error: --color: 'blue' isn't one of red, dark-red.\n"
        "Run 'paint --help' for usage.\n"
    )
    assert "--color [red|dark-red]" in run(paint, ["--help"]).stdout


def test_choices_narrows_a_literal_and_checks_numbers() -> None:
    @command("pick")
    @option("mode")
    @choices("fast")
    @option("level")
    @choices(1, 2)
    @option("ratio")
    @choices(1, 0.5)
    def pick(
        mode: Literal["fast", "slow"] = "fast", level: int = 1, ratio: float = 1
    ) -> str:
        return f"{mode} {level} {ratio}"

    assert run(pick, ["--level", "2", "--ratio", "0.5"]).stdout == "fast 2 0.5\n"
    assert run(pick, ["--mode", "slow", "--level", "3"]).stderr == (
        "error: --mode: 'slow' isn't one of fast.\n"
        "error: --level: 3 isn't one of 1, 2.\n"
        "Run 'pick --help' for usage.\n"
    )


def test_choices_of_paths() -> None:
    @command("open")
    @argument("config")
    @choices(Path("a.toml"), Path("b.toml"))
    def open_config(config: Path) -> str:
        return config.name

    assert run(open_config, ["b.toml"]).stdout == "b.toml\n"
    assert run(open_config, ["c.toml"]).returncode == 2


@pytest.mark.parametrize(
    ("annotation", "bounds", "good", "bad", "error"),
    [
        (
            date,
            (START, END),
            "2026-10-25",
            "2019-12-31",
            "2019-12-31 isn't between 2020-01-01 and 2030-12-31.",
        ),
        (
            datetime,
            (datetime.fromisoformat("2020-01-01 09:00"), None),
            "2026-10-25 10:00",
            "2019-01-01 10:00",
            "2019-01-01 10:00:00 is less than 2020-01-01 09:00:00.",
        ),
        (
            time,
            (None, time(17)),
            "09:30",
            "18:00",
            "18:00:00 is more than 17:00:00.",
        ),
    ],
)
def test_between_dates_and_times(
    annotation: object,
    bounds: tuple[date | time | None, date | time | None],
    good: str,
    bad: str,
    error: str,
) -> None:
    def when(moment: object) -> str:
        return str(moment)

    when.__annotations__["moment"] = annotation
    cli = command("when")(option("moment")(between(*bounds)(when)))

    assert run(cli, ["--moment", good]).returncode == 0
    assert run(cli, ["--moment", bad]).stderr == (
        f"error: --moment: {error}\nRun 'when --help' for usage.\n"
    )


def test_children_check_each_item_and_each_line_of_stdin() -> None:
    @command("sum")
    @option("weight")
    @between(1, 10)
    @stdin("numbers")
    @between(low=0)
    def total(numbers: list[int], weight: tuple[int, ...] = ()) -> int:
        return sum(numbers) * (sum(weight) or 1)

    result = run(total, ["--weight", "0", "--weight", "11"], input="1\n-2\n3\n-4\n")

    assert result.stderr == (
        "error: --weight: 0 isn't between 1 and 10.\n"
        "error: --weight: 11 isn't between 1 and 10.\n"
        "error: stdin: line 2: -2 is less than 0.\n"
        "error: stdin: line 4: -4 is less than 0.\n"
        "Run 'sum --help' for usage.\n"
    )


def test_children_follow_the_inputs_label() -> None:
    @command("pick")
    @argument("count")
    @between(1, 5)
    @env("level")
    @between(1, 3)
    def pick(count: int, level: int = 1) -> str:
        return f"{count} {level}"

    result = run(pick, ["9"], env={"LEVEL": "7"})

    assert result.stderr == (
        "error: COUNT: 9 isn't between 1 and 5.\n"
        "error: $LEVEL: 7 isn't between 1 and 3.\n"
        "Run 'pick --help' for usage.\n"
    )


def test_a_counting_flag_can_be_capped() -> None:
    @command("talk")
    @flag("verbose", "-v")
    @between(0, 2)
    def talk(*, verbose: int = 0) -> int:
        return verbose

    assert run(talk, ["-vv"]).stdout == "2\n"
    assert run(talk, ["-vvv"]).stderr == (
        "error: --verbose: 3 isn't between 0 and 2.\nRun 'talk --help' for usage.\n"
    )


def test_several_children_run_top_down_and_stop_at_the_first_problem() -> None:
    @command("tag")
    @option("label")
    @matches(r"[a-z]+")
    @length(high=3)
    def tag(label: str = "x") -> str:
        return label

    assert run(tag, ["--label", "ABCDEF"]).stderr == (
        "error: --label: 'ABCDEF' doesn't match [a-z]+.\nRun 'tag --help' for usage.\n"
    )
    assert run(tag, ["--label", "abcdef"]).stderr == (
        "error: --label: 'abcdef' is longer than 3 characters.\n"
        "Run 'tag --help' for usage.\n"
    )


@CHECKS
@pytest.mark.parametrize(
    ("make", "message"),
    [
        (
            lambda: _one(between(1, 100), int, 0),
            (
                "@between(1, 100) rejects the default of parameter 'value': "
                "0 isn't between 1 and 100. Change one of them."
            ),
        ),
        (
            lambda: _one(matches("[a-z]+"), str, "My Label"),
            (
                "@matches(\"[a-z]+\") rejects the default of parameter 'value': "
                "'My Label' doesn't match [a-z]+. Change one of them."
            ),
        ),
        (
            lambda: _one(choices("a", "b"), tuple[str, ...], ("a", "c")),
            (
                '@choices("a", "b") rejects an item of the default of '
                "parameter 'value': 'c' isn't one of a, b. Change one of them."
            ),
        ),
    ],
    ids=["scalar", "pattern", "collection"],
)
def test_a_bad_default_is_a_definition_error(
    check: Check, make: Callable[[], Check], message: str
) -> None:
    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(make())


def test_a_none_default_isnt_checked() -> None:
    @command("pick")
    @option("keep")
    @between(1, 100)
    def pick(keep: int | None = None) -> str:
        return str(keep)

    validate(pick)


Bad = tuple[
    Callable[..., object], tuple[object, ...], dict[str, object], type[Exception], str
]

BAD_ARGUMENTS: dict[str, Bad] = {
    "between text": (
        between,
        ("a", "z"),
        {},
        TypeError,
        (
            "@between takes numbers, dates or times as bounds, "
            "such as @between(1, 100), not 'a'."
        ),
    ),
    "between bool": (
        between,
        (True,),
        {},
        TypeError,
        (
            "@between takes numbers, dates or times as bounds, "
            "such as @between(1, 100), not True."
        ),
    ),
    "between mixed": (
        between,
        (1, END),
        {},
        TypeError,
        (
            "@between(1, datetime.date(2030, 12, 31)) mixes bound types. "
            "Use two numbers, two dates or two times."
        ),
    ),
    "between date and datetime": (
        between,
        (START, datetime.fromisoformat("2030-01-01 00:00")),
        {},
        TypeError,
        (
            "@between(datetime.date(2020, 1, 1), "
            "datetime.datetime(2030, 1, 1, 0, 0)) mixes bound types. "
            "Use two numbers, two dates or two times."
        ),
    ),
    "between none": (
        between,
        (),
        {},
        TypeError,
        "@between needs a bound, such as @between(1, 100) or @between(low=1).",
    ),
    "between reversed": (
        between,
        (100, 1),
        {},
        ValueError,
        "@between(100, 1) has its bounds the wrong way round. Use @between(1, 100).",
    ),
    "length float": (
        length,
        (2.5,),
        {},
        TypeError,
        "@length takes whole numbers as bounds, such as @length(3, 20), not 2.5.",
    ),
    "length zero low": (
        length,
        (0, 20),
        {},
        ValueError,
        "@length takes bounds of 1 or more, such as @length(1, 20), not 0.",
    ),
    "length zero high": (
        length,
        (),
        {"high": 0},
        ValueError,
        "@length takes bounds of 1 or more, such as @length(1, 20), not 0.",
    ),
    "length none": (
        length,
        (),
        {},
        TypeError,
        "@length needs a bound, such as @length(3, 20) or @length(low=1).",
    ),
    "length reversed": (
        length,
        (20, 3),
        {},
        ValueError,
        "@length(20, 3) has its bounds the wrong way round. Use @length(3, 20).",
    ),
    "matches number": (
        matches,
        (1,),
        {},
        TypeError,
        '@matches takes a pattern as a string, such as @matches(r"[a-z]+"), not 1.',
    ),
    "matches invalid": (
        matches,
        ("[a-",),
        {},
        ValueError,
        (
            '@matches("[a-") isn\'t a valid pattern: unterminated character set '
            "at position 0."
        ),
    ),
    "choices none": (
        choices,
        (),
        {},
        TypeError,
        '@choices needs values, such as @choices("zip", "tar").',
    ),
    "choices empty list": (
        choices,
        ([],),
        {},
        TypeError,
        '@choices needs values, such as @choices("zip", "tar").',
    ),
    "choices twice": (
        choices,
        ("a", "a"),
        {},
        ValueError,
        '@choices("a", "a") lists \'a\' twice. Remove one.',
    ),
    "choices mixed": (
        choices,
        (Color, "x"),
        {},
        TypeError,
        (
            '@choices(Color, "x") mixes a collection with values. '
            "Pass the values one by one, or one collection."
        ),
    ),
    "choices range": (
        choices,
        (range(1, 11),),
        {},
        TypeError,
        "@choices takes no range. Use @between(1, 10) instead.",
    ),
    "choices stepped range": (
        choices,
        (range(0, 60, 15),),
        {},
        TypeError,
        "@choices takes no range. List its values with @choices(*range(0, 60, 15)).",
    ),
}


@pytest.mark.parametrize("case", BAD_ARGUMENTS)
def test_children_reject_bad_arguments(case: str) -> None:
    child, arguments, keywords, error, message = BAD_ARGUMENTS[case]

    with pytest.raises(error, match=exactly(message)):
        _ = child(*arguments, **keywords)


@pytest.mark.parametrize(
    ("child", "message"),
    [
        (
            between,
            "@between needs its bounds in parentheses, such as @between(1, 100).",
        ),
        (length, "@length needs its bounds in parentheses, such as @length(3, 20)."),
        (
            matches,
            '@matches needs a pattern in parentheses, such as @matches(r"[a-z]+").',
        ),
        (
            choices,
            '@choices needs its values in parentheses, such as @choices("zip", "tar").',
        ),
    ],
)
def test_a_child_without_parentheses_is_rejected(
    child: Callable[..., object], message: str
) -> None:
    def pick(keep: int = 1) -> int:
        return keep

    with pytest.raises(TypeError, match=exactly(message)):
        _ = child(pick)


def test_a_child_above_every_parent_is_rejected() -> None:
    @between(1, 100)
    @option("keep")
    def pick(keep: int = 1) -> int:
        return keep

    message = (
        "@between(1, 100) is above every parent, so it has nothing to check. "
        "Put it right below the parent whose value it checks."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("pick")(pick)


def test_a_child_above_the_root_decorator_is_rejected() -> None:
    @command("pick")
    def pick() -> None: ...

    message = (
        "@length(low=3) must decorate a function, so it goes below @command or @group."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = length(3)(pick)


@CHECKS
@pytest.mark.parametrize(
    ("make", "message"),
    [
        (
            lambda: _one(between(1, 100), str, "x"),
            (
                "@between(1, 100) checks numbers, dates or times, "
                "but parameter 'value' has the type str."
            ),
        ),
        (
            lambda: _one(between(1, 100), date, START),
            (
                "@between(1, 100) has int bounds, but parameter 'value' has the type "
                "date. Use date bounds."
            ),
        ),
        (
            lambda: _one(between(0.5, 2), int, 1),
            (
                "@between(0.5, 2) has float bounds, but parameter 'value' has the type "
                "int. Use int bounds."
            ),
        ),
        (
            lambda: _one(matches("[a-z]+"), int, 1),
            "@matches(\"[a-z]+\") checks text, but parameter 'value' has the type int.",
        ),
        (
            lambda: _one(length(3, 20), int, 1),
            "@length(3, 20) checks text, but parameter 'value' has the type int.",
        ),
        (
            lambda: _one(choices("1", "2"), int, 1),
            (
                "@choices(\"1\", \"2\") lists '1', a str, but parameter 'value' "
                "has the type int. Use int values."
            ),
        ),
        (
            lambda: _one(choices("c"), Literal["a", "b"], "a"),
            "@choices(\"c\") lists 'c', but parameter 'value' only takes 'a', 'b'.",
        ),
        (
            lambda: _one(choices(Color), Color, Color.RED),
            (
                "@choices(Color) allows every member of Color, which the annotation "
                "already does. Remove it."
            ),
        ),
        (
            lambda: _one(choices(Color), str, "red"),
            (
                "@choices(Color) lists members of Color, but parameter 'value' has the "
                "type str. Annotate it as Color instead."
            ),
        ),
    ],
)
def test_a_child_that_doesnt_fit_its_parameter_is_rejected(
    check: Check, make: Callable[[], Check], message: str
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(make())


@CHECKS
def test_a_child_below_a_bool_flag_is_rejected(check: Check) -> None:
    @command("talk")
    @flag("quiet", "-q")
    @between(0, 3)
    def talk(*, quiet: bool = False) -> bool:
        return quiet

    message = (
        '@between(0, 3) is below @flag("quiet"), a bool, which has nothing to '
        "check. Remove it."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(talk)


def _one(
    child: Callable[[Callable[..., object]], Callable[..., object]],
    annotation: object,
    default: object,
) -> Check:
    def pick(value: object = default) -> object:
        return value

    pick.__annotations__["value"] = annotation
    return command("pick")(option("value")(child(pick)))
