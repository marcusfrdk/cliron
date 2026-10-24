import pytest

from cliron import argument, command, flag, option
from cliron.testing import run


def test_bundled_flag_and_option_reach_the_command() -> None:
    @command("greet")
    @argument("name")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(name: str, count: int = 1, *, shout: bool = False) -> str:
        message = f"Hello, {name}!"
        return "\n".join([message.upper() if shout else message] * count)

    result = run(greet, ["Ada", "-sc2"])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "HELLO, ADA!\nHELLO, ADA!\n",
        "",
    )


def test_every_input_error_is_reported_at_once() -> None:
    calls: list[tuple[str, int, bool]] = []

    @command("greet")
    @argument("name")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(name: str, count: int = 1, *, shout: bool = False) -> None:
        calls.append((name, count, shout))

    result = run(greet, ["--count", "two", "--shot"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: NAME is required.\n"
        "error: --count: 'two' isn't a whole number.\n"
        "error: unknown option '--shot'. Did you mean '--shout'?\n"
    )
    assert calls == []


@pytest.mark.parametrize(
    "args", [["--count=3"], ["--count", "3"], ["-c3"], ["-c", "3"]]
)
def test_option_value_can_be_attached_or_separate(args: list[str]) -> None:
    calls: list[int] = []

    @command("repeat")
    @option("count", "-c")
    def repeat(count: int = 1) -> None:
        calls.append(count)

    result = run(repeat, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [3]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-sc2"], (True, 2, 0)),
        (["-sc", "2"], (True, 2, 0)),
        (["-vvs"], (True, 1, 2)),
        (["-vsvc3"], (True, 3, 2)),
    ],
)
def test_short_flags_bundle_and_an_option_may_end_the_bundle(
    args: list[str], expected: tuple[bool, int, int]
) -> None:
    calls: list[tuple[bool, int, int]] = []

    @command("greet")
    @option("count", "-c")
    @flag("shout", "-s")
    @flag("verbose", "-v")
    def greet(count: int = 1, verbose: int = 0, *, shout: bool = False) -> None:
        calls.append((shout, count, verbose))

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [expected]


@pytest.mark.parametrize(
    "args",
    [
        ["Ada", "Lovelace", "--count", "2", "--shout"],
        ["--shout", "Ada", "-c2", "Lovelace"],
        ["-c", "2", "Ada", "-s", "Lovelace"],
        ["Ada", "--count=2", "Lovelace", "-s"],
    ],
)
def test_options_flags_and_arguments_mix_in_any_order(args: list[str]) -> None:
    calls: list[tuple[str, str, int, bool]] = []

    @command("greet")
    @argument("first")
    @argument("last")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(first: str, last: str, count: int = 1, *, shout: bool = False) -> None:
        calls.append((first, last, count, shout))

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("Ada", "Lovelace", 2, True)]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["a"], ("a", "out.txt")),
        (["a", "b"], ("a", "b")),
    ],
)
def test_arguments_fill_left_to_right(
    args: list[str], expected: tuple[str, str]
) -> None:
    calls: list[tuple[str, str]] = []

    @command("copy")
    @argument("source")
    @argument("destination")
    def copy(source: str, destination: str = "out.txt") -> None:
        calls.append((source, destination))

    result = run(copy, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [expected]


def test_list_argument_takes_the_remaining_words_around_options() -> None:
    calls: list[tuple[str, list[str], bool]] = []

    @command("move")
    @argument("destination")
    @argument("sources")
    @flag("force", "-f")
    def move(destination: str, sources: list[str], *, force: bool = False) -> None:
        calls.append((destination, sources, force))

    result = run(move, ["out", "a", "-f", "b", "c"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("out", ["a", "b", "c"], True)]


@pytest.mark.parametrize("args", [["-c=3"], ["-sc=3"]])
def test_short_option_with_an_equals_sign_is_an_error(args: list[str]) -> None:
    calls: list[tuple[int, bool]] = []

    @command("greet")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(count: int = 1, *, shout: bool = False) -> None:
        calls.append((count, shout))

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: Use -c3 or -c 3 instead of -c=3.\n",
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-5"], (-5.0, 0.0)),
        (["-.5"], (-0.5, 0.0)),
        (["1", "--offset", "-5"], (1.0, -5.0)),
        (["1", "-o", "-.5"], (1.0, -0.5)),
        (["--offset", "-.5", "-5"], (-5.0, -0.5)),
    ],
)
def test_negative_numbers_are_values(
    args: list[str], expected: tuple[float, float]
) -> None:
    calls: list[tuple[float, float]] = []

    @command("shift")
    @argument("amount")
    @option("offset", "-o")
    def shift(amount: float, offset: float = 0.0) -> None:
        calls.append((amount, offset))

    result = run(shift, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [expected]


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--name", "-x"], "--name needs a value. To pass '-x', write --name=-x."),
        (["-n", "-x"], "--name needs a value. To pass '-x', write --name=-x."),
        (
            ["--name", "--exclaim"],
            "--name needs a value. To pass '--exclaim', write --name=--exclaim.",
        ),
        (
            ["--name", "-z"],
            (
                "--name needs a value. To pass '-z', write --name=-z.\n"
                "error: unknown option '-z'."
            ),
        ),
    ],
)
def test_option_value_cannot_start_with_a_dash(args: list[str], error: str) -> None:
    calls: list[tuple[str, bool]] = []

    @command("greet")
    @option("name", "-n")
    @flag("exclaim", "-x")
    def greet(name: str = "World", *, exclaim: bool = False) -> None:
        calls.append((name, exclaim))

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        f"error: {error}\n",
    )
    assert calls == []


def test_value_starting_with_a_dash_can_follow_an_equals_sign() -> None:
    calls: list[tuple[str, bool]] = []

    @command("greet")
    @option("name", "-n")
    @flag("exclaim", "-x")
    def greet(name: str = "World", *, exclaim: bool = False) -> None:
        calls.append((name, exclaim))

    result = run(greet, ["--name=-x"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("-x", False)]


@pytest.mark.parametrize("args", [["--count"], ["-c"], ["-sc"], ["-s", "--count"]])
def test_option_at_the_end_of_the_line_needs_a_value(args: list[str]) -> None:
    calls: list[tuple[int, bool]] = []

    @command("greet")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(count: int = 1, *, shout: bool = False) -> None:
        calls.append((count, shout))

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --count needs a value.\n",
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--shout=yes"], "--shout doesn't take a value."),
        (["--shout="], "--shout doesn't take a value."),
        (["--verbose=2"], "--verbose doesn't take a value."),
        (["-s=yes"], "--shout doesn't take a value."),
    ],
)
def test_flag_given_a_value_is_an_error(args: list[str], error: str) -> None:
    calls: list[tuple[bool, int]] = []

    @command("greet")
    @flag("shout", "-s")
    @flag("verbose", "-v")
    def greet(verbose: int = 0, *, shout: bool = False) -> None:
        calls.append((shout, verbose))

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        f"error: {error}\n",
    )
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [
        ["--count", "1", "--count", "2"],
        ["--count=1", "-c2", "-c", "3"],
    ],
)
def test_plain_option_given_twice_is_reported_once(args: list[str]) -> None:
    calls: list[int] = []

    @command("repeat")
    @option("count", "-c")
    def repeat(count: int = 1) -> None:
        calls.append(count)

    result = run(repeat, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --count can only be given once.\n",
    )
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [
        ["--shout", "--shout"],
        ["-s", "-s", "-s"],
        ["-sss"],
        ["--shout", "-ss"],
    ],
)
def test_bool_flag_given_twice_is_reported_once(args: list[str]) -> None:
    calls: list[bool] = []

    @command("greet")
    @flag("shout", "-s")
    def greet(*, shout: bool = False) -> None:
        calls.append(shout)

    result = run(greet, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --shout can only be given once.\n",
    )
    assert calls == []


def test_collection_option_collects_every_occurrence() -> None:
    calls: list[tuple[str, ...]] = []

    @command("tag")
    @option("tag", "-t")
    def tag(tag: tuple[str, ...] = ()) -> None:
        calls.append(tag)

    result = run(tag, ["--tag", "a", "-tb", "--tag=c", "-t", "d"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("a", "b", "c", "d")]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], 0),
        (["-v"], 1),
        (["-vvv"], 3),
        (["-v", "-v"], 2),
        (["--verbose", "--verbose"], 2),
        (["-v", "--verbose", "-vv"], 4),
    ],
)
def test_int_flag_counts_how_often_it_is_given(args: list[str], expected: int) -> None:
    calls: list[int] = []

    @command("build")
    @flag("verbose", "-v")
    def build(verbose: int = 0) -> None:
        calls.append(verbose)

    result = run(build, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [expected]


@pytest.mark.parametrize(
    ("args", "words", "shout"),
    [
        (["--", "-x"], ["-x"], False),
        (["--", "-x", "--"], ["-x", "--"], False),
        (["--", "--shout", "-s"], ["--shout", "-s"], False),
        (["a", "--", "b"], ["a", "b"], False),
        (["-s", "--", "-s"], ["-s"], True),
    ],
)
def test_double_dash_ends_options(
    args: list[str], words: list[str], *, shout: bool
) -> None:
    calls: list[tuple[list[str], bool]] = []

    @command("echo")
    @argument("words")
    @flag("shout", "-s")
    def echo(words: list[str], *, shout: bool = False) -> None:
        calls.append((words, shout))

    result = run(echo, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [(words, shout)]


def test_word_after_double_dash_is_never_an_option() -> None:
    calls: list[tuple[str, bool]] = []

    @command("greet")
    @argument("name")
    @flag("shout", "-s")
    def greet(name: str, *, shout: bool = False) -> None:
        calls.append((name, shout))

    result = run(greet, ["Ada", "--", "--shout"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unexpected argument '--shout'.\n",
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-"], ("-", "out.txt")),
        (["in.txt", "--output", "-"], ("in.txt", "-")),
        (["in.txt", "-o", "-"], ("in.txt", "-")),
    ],
)
def test_lone_dash_is_a_value(args: list[str], expected: tuple[str, str]) -> None:
    calls: list[tuple[str, str]] = []

    @command("copy")
    @argument("source")
    @option("output", "-o")
    def copy(source: str, output: str = "out.txt") -> None:
        calls.append((source, output))

    result = run(copy, args)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [expected]


@pytest.mark.parametrize("args", [["--cou"], ["--cou=3"], ["--cou", "3"]])
def test_long_options_cannot_be_abbreviated(args: list[str]) -> None:
    calls: list[int] = []

    @command("repeat")
    @option("count", "-c")
    def repeat(count: int = 1) -> None:
        calls.append(count)

    result = run(repeat, args)

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '--cou'. Did you mean '--count'?\n",
    )
    assert calls == []


def test_unknown_option_without_a_close_match_has_no_suggestion() -> None:
    calls: list[int] = []

    @command("repeat")
    @option("count", "-c")
    def repeat(count: int = 1) -> None:
        calls.append(count)

    result = run(repeat, ["--colour=red"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '--colour'.\n",
    )
    assert calls == []


def test_unknown_short_option_is_reported() -> None:
    calls: list[tuple[str, bool]] = []

    @command("greet")
    @argument("name")
    @flag("shout", "-s")
    def greet(name: str, *, shout: bool = False) -> None:
        calls.append((name, shout))

    result = run(greet, ["Ada", "-x"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '-x'.\n",
    )
    assert calls == []


def test_unknown_option_takes_a_value_when_its_closest_match_does() -> None:
    calls: list[tuple[str, str | None]] = []

    @command("add")
    @argument("title")
    @option("tag")
    def add(title: str, tag: str | None = None) -> None:
        calls.append((title, tag))

    result = run(add, ["--tags", "errands"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: TITLE is required.\n"
        "error: unknown option '--tags'. Did you mean '--tag'?\n"
    )
    assert calls == []


def test_unknown_option_takes_no_value_when_its_closest_match_is_a_flag() -> None:
    calls: list[tuple[str, bool]] = []

    @command("greet")
    @argument("name")
    @flag("shout")
    def greet(name: str, *, shout: bool = False) -> None:
        calls.append((name, shout))

    result = run(greet, ["--shoutt", "x"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '--shoutt'. Did you mean '--shout'?\n",
    )
    assert calls == []


def test_unknown_letter_inside_a_bundle_is_reported() -> None:
    calls: list[tuple[int, bool]] = []

    @command("greet")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(count: int = 1, *, shout: bool = False) -> None:
        calls.append((count, shout))

    result = run(greet, ["-sxc2"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '-x'.\n",
    )
    assert calls == []


def test_each_extra_word_is_an_unexpected_argument() -> None:
    calls: list[str] = []

    @command("greet")
    @argument("name")
    def greet(name: str) -> None:
        calls.append(name)

    result = run(greet, ["Ada", "x", "y"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: unexpected argument 'x'.\nerror: unexpected argument 'y'.\n"
    )
    assert calls == []


def test_command_without_arguments_rejects_a_word() -> None:
    calls: list[bool] = []

    @command("status")
    @flag("short", "-s")
    def status(*, short: bool = False) -> None:
        calls.append(short)

    result = run(status, ["-s", "x"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unexpected argument 'x'.\n",
    )
    assert calls == []


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], "error: FILE_NAME is required.\nerror: DESTINATION is required.\n"),
        (["a"], "error: DESTINATION is required.\n"),
    ],
)
def test_missing_required_arguments_are_reported(
    args: list[str], expected: str
) -> None:
    calls: list[tuple[str, str]] = []

    @command("copy")
    @argument("file_name")
    @argument("destination")
    def copy(file_name: str, destination: str) -> None:
        calls.append((file_name, destination))

    result = run(copy, args)

    assert (result.returncode, result.stdout, result.stderr) == (2, "", expected)
    assert calls == []


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], "error: --host is required.\nerror: --api-key is required.\n"),
        (["--api-key", "k"], "error: --host is required.\n"),
    ],
)
def test_missing_required_options_are_reported(args: list[str], expected: str) -> None:
    calls: list[tuple[str, str]] = []

    @command("connect")
    @option("host")
    @option("api_key")
    def connect(host: str, api_key: str) -> None:
        calls.append((host, api_key))

    result = run(connect, args)

    assert (result.returncode, result.stdout, result.stderr) == (2, "", expected)
    assert calls == []


def test_errors_list_declared_inputs_first_then_unplaced_words_in_order() -> None:
    calls: list[tuple[int, int, str, bool]] = []

    @command("deploy")
    @argument("port")
    @option("count", "-c")
    @option("host")
    @flag("force", "-f")
    def deploy(port: int, count: int, host: str, *, force: bool = False) -> None:
        calls.append((port, count, host, force))

    result = run(deploy, ["-ff", "-q", "eighty", "surplus", "--zzz", "--count", "two"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: PORT: 'eighty' isn't a whole number.\n"
        "error: --count: 'two' isn't a whole number.\n"
        "error: --host is required.\n"
        "error: --force can only be given once.\n"
        "error: unknown option '-q'.\n"
        "error: unexpected argument 'surplus'.\n"
        "error: unknown option '--zzz'.\n"
    )
    assert calls == []


def test_values_reach_positional_or_keyword_parameters() -> None:
    calls: list[tuple[str, str, int]] = []

    @command("copy")
    @argument("source")
    @option("mode", "-m")
    @flag("verbose", "-v")
    def copy(source: str, mode: str = "fast", verbose: int = 0) -> None:
        calls.append((source, mode, verbose))

    result = run(copy, ["-vv", "a.txt", "--mode", "safe"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("a.txt", "safe", 2)]


def test_values_reach_keyword_only_parameters() -> None:
    calls: list[tuple[str, str, bool]] = []

    @command("copy")
    @argument("source")
    @option("mode", "-m")
    @flag("force", "-f")
    def copy(*, source: str, mode: str = "fast", force: bool = False) -> None:
        calls.append((source, mode, force))

    result = run(copy, ["-f", "a.txt", "-m", "safe"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("a.txt", "safe", True)]


def test_arguments_follow_decorator_order_across_parameter_kinds() -> None:
    calls: list[tuple[str, str]] = []

    @command("copy")
    @argument("source")
    @argument("destination")
    def copy(destination: str, *, source: str) -> None:
        calls.append((source, destination))

    result = run(copy, ["a.txt", "b.txt"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert calls == [("a.txt", "b.txt")]


@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        (["-v=1"], "error: --verbose doesn't take a value.\n"),
        (["-qv=1"], "error: --verbose doesn't take a value.\n"),
    ],
)
def test_short_counting_flag_given_a_value_is_an_error(
    args: list[str], stderr: str
) -> None:
    @command("tool")
    @flag("verbose", "-v")
    @flag("quiet", "-q")
    def tool(verbose: int = 0, *, quiet: bool = False) -> str:
        return f"{verbose} {quiet}"

    result = run(tool, args)

    assert (result.returncode, result.stdout, result.stderr) == (2, "", stderr)


def test_unknown_short_option_with_an_equals_sign_takes_the_rest_as_its_value() -> None:
    @command("greet")
    @argument("name")
    def greet(name: str) -> str:
        return name

    result = run(greet, ["Ada", "-x=5"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '-x'.\n",
    )


def test_short_option_with_an_empty_value_after_equals_needs_a_value() -> None:
    @command("greet")
    @option("count", "-c")
    def greet(count: int = 1) -> str:
        return str(count)

    result = run(greet, ["-c="])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --count needs a value.\n",
    )


def test_conversion_errors_are_reported_next_to_other_errors_of_the_same_option() -> (
    None
):
    @command("sum")
    @option("number", "-n")
    def total(number: list[int] | None = None) -> str:
        return str(number)

    result = run(total, ["--number", "1x", "--number"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --number needs a value.\nerror: --number: '1x' isn't a whole number.\n",
    )


@pytest.mark.parametrize("word", ["-1abc", "-.hidden"])
def test_word_starting_with_a_dash_is_an_option_unless_it_is_a_number(
    word: str,
) -> None:
    @command("echo")
    @argument("text")
    @option("count", "-c")
    def echo(text: str, count: int = 1) -> str:
        return text * count

    result = run(echo, ["x", "--count", word])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        (
            f"error: --count needs a value. To pass {word!r}, write --count={word}.\n"
            f"error: unknown option {word!r}.\n"
        ),
    )


def test_number_that_isnt_whole_is_a_value_for_an_int_option() -> None:
    @command("echo")
    @option("count", "-c")
    def echo(count: int = 1) -> str:
        return str(count)

    result = run(echo, ["--count", "-1e3"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: --count: '-1e3' isn't a whole number.\n",
    )


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["-s", "-s=1"], "--shout doesn't take a value."),
        (["--shout", "--shout=yes"], "--shout doesn't take a value."),
        (["-c", "1", "-c=2"], "Use -c2 or -c 2 instead of -c=2."),
        (["--count", "1", "--count"], "--count needs a value."),
    ],
)
def test_malformed_repeat_is_also_reported_as_given_twice(
    args: list[str], error: str
) -> None:
    @command("greet")
    @option("count", "-c")
    @flag("shout", "-s")
    def greet(count: int = 1, *, shout: bool = False) -> str:
        return f"{count} {shout}"

    result = run(greet, args)

    once = "--shout" if "shout" in error else "--count"
    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        f"error: {once} can only be given once.\nerror: {error}\n",
    )


@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        (["--host"], "error: --host needs a value.\n"),
        (
            ["--host", "-x"],
            (
                "error: --host needs a value. To pass '-x', write --host=-x.\n"
                "error: unknown option '-x'.\n"
            ),
        ),
    ],
)
def test_required_option_without_a_value_is_reported_once(
    args: list[str], stderr: str
) -> None:
    @command("connect")
    @option("host")
    def connect(host: str) -> str:
        return host

    result = run(connect, args)

    assert (result.returncode, result.stdout, result.stderr) == (2, "", stderr)


def test_long_option_value_may_contain_equals_signs() -> None:
    @command("define")
    @option("define", "-D")
    def define(define: str) -> str:
        return define

    result = run(define, ["--define=key=value"])

    assert (result.returncode, result.stdout, result.stderr) == (0, "key=value\n", "")


def test_dash_followed_by_a_non_letter_is_one_unknown_option() -> None:
    @command("echo")
    @argument("text")
    def echo(text: str) -> str:
        return text

    result = run(echo, ["x", "-\N{LATIN SMALL LETTER E WITH ACUTE}"])

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unknown option '-\N{LATIN SMALL LETTER E WITH ACUTE}'.\n",
    )


def test_trailing_underscore_isnt_part_of_what_users_type() -> None:
    @command("copy")
    @argument("class_")
    @option("from_")
    @flag("in_")
    def copy(class_: str, from_: str = "here", *, in_: bool = False) -> str:
        return f"{class_} {from_} {in_}"

    result = run(copy, ["box", "--from", "there", "--in"])
    missing = run(copy, [])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "box there True\n",
        "",
    )
    assert (missing.returncode, missing.stderr) == (2, "error: CLASS is required.\n")
