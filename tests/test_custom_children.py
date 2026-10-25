import re
import sys
from collections.abc import Callable
from functools import partial
from typing import Literal
from uuid import UUID

import pytest

from cliron import Child, argument, between, child, command, flag, option, stdin
from cliron.testing import run, validate

Check = Callable[..., object]

CHECKS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@child
def slug(value: str, separator: str = "-") -> str:
    return separator.join(value.lower().split())


@child
def shout(value: str) -> str:
    return value.upper()


@child
def even(value: int) -> int:
    if value % 2:
        message = f"{value} isn't even."
        raise ValueError(message)
    return value


@child
def parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        message = f"{value!r} isn't a UUID."
        raise ValueError(message) from None


@child
def hexadecimal(value: str) -> int:
    try:
        return int(value, 16)
    except ValueError:
        message = f"{value!r} isn't a hexadecimal number."
        raise ValueError(message) from None


@child
def stringify(value: int) -> object:
    return str(value)


@child
def blank_as_none(value: str) -> str | None:
    return value or None


@child
def positive(value: int) -> object:
    return value > 0


@child
def lengths(value: str) -> dict[str, int]:
    return {word: len(word) for word in value.split(",")}


class Multiple(Child[int, int]):
    def __init__(self, factor: int) -> None:
        self.factor: int = factor

    def process(self, value: int, /) -> int:
        if value % self.factor:
            message = f"{value} isn't a multiple of {self.factor}."
            raise ValueError(message)
        return value

    def describe(self) -> str:
        return f"A multiple of {self.factor}."


@command("permalink")
@argument("title")
@slug()
@option("tag")
@slug(separator="_")
def permalink(title: str, tag: str = "Misc") -> str:
    return f"/{tag}/{title}"


@command("pick")
@option("count", "-c", help="How many.")
@even()
@option("size", "-s", help="Box size.")
@Multiple(3)
def pick(count: int = 2, size: int = 3) -> str:
    return f"{count} {size}"


@command("show")
@argument("keys")
@parse_uuid()
@option("parent", "-p")
@parse_uuid()
@option("skip", "-s")
@parse_uuid()
def show(
    keys: list[UUID], parent: UUID | None = None, skip: tuple[UUID, ...] = ()
) -> str:
    found = parent.int if parent else None
    return f"{[key.int for key in keys]} {found} {[key.int for key in skip]}"


@command("paint")
@option("red", "-r")
@hexadecimal()
@between(0, 255)
@option("level")
@hexadecimal()
def paint(red: int = 0, level: Literal[1, 2] = 1) -> str:
    return f"{red} {level}"


def uuid(number: int) -> str:
    return str(UUID(int=number))


def test_a_function_child_changes_the_value() -> None:
    result = run(permalink, ["Hello World", "--tag", "Big News"])

    assert result.stdout == "/big_news/hello-world\n"


def test_a_default_reaches_the_function_unchanged() -> None:
    assert run(permalink, ["Hello World"]).stdout == "/Misc/hello-world\n"


def test_children_report_a_bad_value_after_the_label() -> None:
    result = run(pick, ["-c", "3", "-s", "4"])

    assert result.returncode == 2
    assert result.stderr == (
        "error: --count: 3 isn't even.\n"
        "error: --size: 4 isn't a multiple of 3.\n"
        "Run 'pick --help' for usage.\n"
    )


def test_children_pass_good_values_on() -> None:
    assert run(pick, ["-c", "4", "-s", "9"]).stdout == "4 9\n"


def test_help_shows_what_a_child_describes() -> None:
    lines = run(pick, ["--help"]).stdout.splitlines()

    assert [line.split(maxsplit=3)[3] for line in lines[3:5]] == [
        "How many. (default: 2)",
        "Box size. A multiple of 3. (default: 3)",
    ]


def test_a_first_child_that_takes_str_converts_the_text() -> None:
    args = [uuid(1), uuid(2), "-p", uuid(3), "-s", uuid(4), "-s", uuid(5)]

    assert run(show, args).stdout == "[1, 2] 3 [4, 5]\n"


def test_a_converting_child_reports_text_it_cant_convert() -> None:
    result = run(show, [uuid(1), "nope"])

    assert result.stderr == (
        "error: KEYS: 'nope' isn't a UUID.\nRun 'show --help' for usage.\n"
    )


def test_a_converting_child_reads_each_line_of_stdin() -> None:
    @command("count")
    @stdin("keys")
    @parse_uuid()
    def count(keys: list[UUID]) -> int:
        return len(keys)

    assert run(count, [], input=f"{uuid(1)}\n{uuid(2)}").stdout == "2\n"


def test_help_names_the_type_a_converting_child_returns() -> None:
    lines = run(show, ["--help"]).stdout.splitlines()

    assert "  -p, --parent UUID" in lines
    assert any(line.startswith("  -s, --skip UUID") for line in lines)


def test_a_converting_child_can_read_another_format_of_a_known_type() -> None:
    assert run(paint, ["-r", "ff", "--level", "2"]).stdout == "255 2\n"
    assert run(paint, ["-r", "1ff"]).stderr == (
        "error: --red: 511 isn't between 0 and 255.\nRun 'paint --help' for usage.\n"
    )


def test_help_keeps_the_placeholder_of_a_known_type() -> None:
    lines = run(paint, ["--help"]).stdout.splitlines()

    assert any(line.startswith("  -r, --red INT") for line in lines)
    assert any(line.startswith("  --level VALUE") for line in lines)


def test_a_child_may_return_none_for_an_optional_parameter() -> None:
    @command("greet")
    @option("name")
    @blank_as_none()
    def greet(name: str | None = "Ada") -> str:
        return f"{name}"

    assert run(greet, ["--name="]).stdout == "None\n"


def test_a_child_that_returns_the_wrong_type_is_printed_as_a_mistake(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def pick(count: int = 1) -> int:
        return count

    cli = command("pick")(option("count")(stringify()(pick)))
    monkeypatch.setattr(sys, "argv", ["cli.py", "--count", "2"])

    with pytest.raises(SystemExit) as info:
        _ = cli()

    assert info.value.code == 1
    assert capsys.readouterr().err == (
        "error: @stringify() returned str, but parameter 'count' has the type int. "
        "Make it return int.\n"
        f"  in command 'pick', defined at {__file__}:{pick.__code__.co_firstlineno}\n"
    )


def test_a_child_that_returns_none_for_a_required_parameter_is_a_mistake() -> None:
    @command("greet")
    @option("name")
    @blank_as_none()
    def greet(name: str) -> str:
        return name

    message = (
        "@blank_as_none() returned None, but parameter 'name' has the type str. "
        "Make it return str."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(greet, ["--name="])


def test_a_child_that_returns_a_bool_for_an_int_is_a_mistake() -> None:
    @command("pick")
    @option("count")
    @positive()
    def pick(count: int = 1) -> int:
        return count

    message = (
        "@positive() returned bool, but parameter 'count' has the type int. "
        "Make it return int."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(pick, ["--count", "2"])


def test_a_converting_child_can_return_any_type() -> None:
    @command("measure")
    @option("words")
    @lengths()
    def measure(words: dict[str, int] | None = None) -> dict[str, int] | None:
        return words

    assert run(measure, ["--words", "a,bc"]).stdout == '{\n  "a": 1,\n  "bc": 2\n}\n'
    assert "  --words VALUE" in run(measure, ["--help"]).stdout.splitlines()


def test_a_child_below_a_counted_flag_must_return_an_int() -> None:
    @command("talk")
    @flag("verbose", "-v")
    @stringify()
    def talk(verbose: int = 0) -> int:
        return verbose

    message = (
        "@stringify() returned str, but parameter 'verbose' has the type int. "
        "Make it return int."
    )
    assert run(talk, []).stdout == "0\n"
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(talk, ["-v"])


@CHECKS
@pytest.mark.parametrize(
    ("make", "message"),
    [
        (
            lambda: _one(even(), str, "a"),
            "@even() takes int, but parameter 'value' has the type str.",
        ),
        (
            lambda: _one(even(), float, 0.5),
            "@even() takes int, but parameter 'value' has the type float.",
        ),
        (
            lambda: _one(Multiple(3), str, "a"),
            "@Multiple() takes int, but parameter 'value' has the type str.",
        ),
        (
            lambda: _one(slug(), int, 1, between(1, 5)),
            "@slug() takes str, but parameter 'value' has the type int.",
        ),
        (
            lambda: _one(slug("_"), int, 1, between(1, 5)),
            "@slug('_') takes str, but parameter 'value' has the type int.",
        ),
    ],
    ids=["str", "float", "class", "second", "options"],
)
def test_a_child_that_doesnt_fit_its_parameter_is_rejected(
    check: Check, make: Callable[[], Check], message: str
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = check(make())


@CHECKS
def test_a_child_that_takes_a_float_fits_an_int(check: Check) -> None:
    @child
    def halve(value: float) -> float:
        return value / 2

    _ = check(_one(halve(), int, 1))


@CHECKS
def test_a_child_that_takes_a_union_fits_each_member(check: Check) -> None:
    @child
    def same(value: int | str) -> int | str:
        return value

    _ = check(_one(same(), int, 1))


@CHECKS
@pytest.mark.parametrize(
    ("make", "message"),
    [
        (
            lambda: _one(even(), int, 3),
            (
                "@even() rejects the default of parameter 'value': 3 isn't even. "
                "Change one of them."
            ),
        ),
        (
            lambda: _one(Multiple(3), tuple[int, ...], (3, 4)),
            (
                "@Multiple() rejects an item of the default of parameter 'value': "
                "4 isn't a multiple of 3. Change one of them."
            ),
        ),
    ],
    ids=["scalar", "collection"],
)
def test_a_child_that_rejects_the_default_is_a_definition_error(
    check: Check, make: Callable[[], Check], message: str
) -> None:
    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(make())


@CHECKS
def test_a_converting_child_doesnt_check_the_default(check: Check) -> None:
    _ = check(_one(parse_uuid(), UUID, UUID(int=0)))


@pytest.mark.parametrize(
    ("above", "below", "message"),
    [
        (
            option("title"),
            slug,
            "@option is above @slug, which needs parentheses: @slug().",
        ),
        (
            command("title"),
            slug,
            "@command is above @slug, which needs parentheses: @slug().",
        ),
        (
            between(1, 5),
            slug,
            "@between(1, 5) is above @slug, which needs parentheses: @slug().",
        ),
        (
            option("title"),
            Multiple,
            "@option is above @Multiple, which needs parentheses: @Multiple().",
        ),
        (option("title"), shout, "@shout needs parentheses: @shout()."),
    ],
    ids=["parent", "root", "child", "class", "no-options"],
)
def test_a_child_without_parentheses_is_rejected(
    above: Callable[..., object], below: Callable[..., object], message: str
) -> None:
    def title(title: str) -> str:
        return title

    with pytest.raises(TypeError, match=exactly(message)):
        _ = above(below(title))


def nothing() -> str:
    return ""


def value_last(*, value: str) -> str:
    return value


@pytest.mark.parametrize(
    ("make", "arguments", "keywords", "message"),
    [
        (
            child,
            (42,),
            {},
            (
                "@child must decorate a function, such as "
                "def slug(value: str) -> str, not 42."
            ),
        ),
        (
            child,
            (nothing,),
            {},
            (
                "@child function 'nothing' must take the value as its first "
                "parameter, such as def nothing(value: str) -> str."
            ),
        ),
        (
            child,
            (value_last,),
            {},
            (
                "@child function 'value_last' must take the value as its first "
                "parameter, such as def value_last(value: str) -> str."
            ),
        ),
        (
            slug,
            (),
            {"separatr": "_"},
            "@slug: got an unexpected keyword argument 'separatr'.",
        ),
        (slug, ("_", "-"), {}, "@slug: too many positional arguments."),
    ],
    ids=["not-a-function", "no-value", "keyword-value", "unknown-option", "too-many"],
)
def test_a_wrong_child_definition_is_rejected(
    make: Check,
    arguments: tuple[object, ...],
    keywords: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = make(*arguments, **keywords)


def _one(
    found: Callable[[Callable[..., object]], Callable[..., object]],
    annotation: object,
    default: object,
    before: Callable[[Callable[..., object]], Callable[..., object]] | None = None,
) -> Check:
    def pick(value: object = default) -> str:
        return f"{value}"

    pick.__annotations__["value"] = annotation
    decorated = found(pick)
    if before is not None:
        decorated = before(decorated)
    return command("pick")(option("value")(decorated))
