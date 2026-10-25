import re
from collections.abc import Callable
from functools import partial

import pytest

from cliron import argument, command, dependency, env, flag, group, option, stdin
from cliron.testing import run, validate

Check = Callable[..., object]

CHECKS = pytest.mark.parametrize(
    "check", [validate, partial(run, args=[])], ids=["validate", "run"]
)

HINT = "Run 'pick --help' for usage.\n"
NOTHING: list[str] = []

CASES = {
    "requires met": ([dependency.requires("a", "b")], ["--a", "--b"], ""),
    "requires without its subject": ([dependency.requires("a", "b")], ["--b"], ""),
    "requires one missing": (
        [dependency.requires("a", "b", "c")],
        ["--a", "--b"],
        "error: --a requires --c.\n",
    ),
    "requires all missing": (
        [dependency.requires("a", "b", "c")],
        ["--a"],
        "error: --a requires --b and --c.\n",
    ),
    "requires_any met": (
        [dependency.requires_any("a", "b", "c")],
        ["--a", "--c"],
        "",
    ),
    "requires_any broken": (
        [dependency.requires_any("a", "b", "c")],
        ["--a"],
        "error: --a requires --b or --c.\n",
    ),
    "conflicts allows the others together": (
        [dependency.conflicts("a", "b", "c")],
        ["--b", "--c"],
        "",
    ),
    "conflicts with one": (
        [dependency.conflicts("a", "b", "c")],
        ["--a", "--c"],
        "error: --a can't be used with --c.\n",
    ),
    "conflicts with several": (
        [dependency.conflicts("a", "b", "c")],
        ["--a", "--b", "--c"],
        "error: --a can't be used with --b and --c.\n",
    ),
    "together none": ([dependency.together("a", "b")], NOTHING, ""),
    "together all": ([dependency.together("a", "b")], ["--a", "--b"], ""),
    "together only one": (
        [dependency.together("a", "b")],
        ["--b"],
        "error: --a and --b must be given together, but only --b was.\n",
    ),
    "together only two": (
        [dependency.together("a", "b", "c")],
        ["--a", "--c"],
        "error: --a, --b and --c must be given together, but only --a and --c were.\n",
    ),
    "alone met": ([dependency.alone("a")], ["--a"], ""),
    "alone with one other": (
        [dependency.alone("a")],
        ["--a", "--d"],
        "error: --a must be given alone, but --d was too.\n",
    ),
    "alone with others": (
        [dependency.alone("a")],
        ["--b", "--a", "--c"],
        "error: --a must be given alone, but --b and --c were too.\n",
    ),
    "at_least met": ([dependency.at_least(1, "a", "b")], ["--b"], ""),
    "at_least none": (
        [dependency.at_least(1, "a", "b")],
        NOTHING,
        "error: at least 1 of --a and --b must be given, but none was.\n",
    ),
    "at_least only": (
        [dependency.at_least(2, "a", "b", "c")],
        ["--b"],
        "error: at least 2 of --a, --b and --c must be given, but only --b was.\n",
    ),
    "at_most met": ([dependency.at_most(1, "a", "b", "c")], ["--c"], ""),
    "at_most some": (
        [dependency.at_most(1, "a", "b", "c")],
        ["--a", "--c"],
        "error: at most 1 of --a, --b and --c can be given, but --a and --c were.\n",
    ),
    "at_most all": (
        [dependency.at_most(2, "a", "b", "c")],
        ["--a", "--b", "--c"],
        "error: at most 2 of --a, --b and --c can be given, but all 3 were.\n",
    ),
    "exactly met": ([dependency.exactly(2, "a", "b", "c")], ["--a", "--c"], ""),
    "exactly none": (
        [dependency.exactly(1, "a", "b")],
        NOTHING,
        "error: exactly 1 of --a and --b must be given, but none was.\n",
    ),
    "exactly both": (
        [dependency.exactly(1, "a", "b")],
        ["--a", "--b"],
        "error: exactly 1 of --a and --b must be given, but both were.\n",
    ),
    "exactly only": (
        [dependency.exactly(2, "a", "b", "c")],
        ["--c"],
        "error: exactly 2 of --a, --b and --c must be given, but only --c was.\n",
    ),
    "exactly all": (
        [dependency.exactly(2, "a", "b", "c")],
        ["--a", "--b", "--c"],
        "error: exactly 2 of --a, --b and --c must be given, but all 3 were.\n",
    ),
    "in the order listed": (
        [dependency.requires("a", "b"), dependency.conflicts("a", "c")],
        ["--a", "--c"],
        "error: --a requires --b.\nerror: --a can't be used with --c.\n",
    ),
}


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@pytest.mark.parametrize("case", CASES)
def test_dependency(case: str) -> None:
    dependencies, args, errors = CASES[case]

    @command("pick", dependencies=dependencies)
    @flag("a")
    @flag("b")
    @flag("c")
    @flag("d")
    def pick(
        *, a: bool = False, b: bool = False, c: bool = False, d: bool = False
    ) -> None:
        _ = (a, b, c, d)

    result = run(pick, args)

    assert (result.returncode, result.stderr) == (
        (2, errors + HINT) if errors else (0, "")
    )


@pytest.mark.parametrize(
    ("args", "code"),
    [(["--x", "1"], 2), ([], 0)],
    ids=["given", "missing"],
)
def test_an_option_counts_as_given_when_it_has_a_word(
    args: list[str], code: int
) -> None:
    @command("pick", dependencies=[dependency.requires("x", "other")])
    @option("x")
    @flag("other")
    def pick(x: str = "default", *, other: bool = False) -> None:
        _ = (x, other)

    assert run(pick, args).returncode == code


@pytest.mark.parametrize(
    ("args", "code"), [(["word"], 2), ([], 0)], ids=["given", "missing"]
)
def test_an_argument_counts_as_given_when_it_has_a_word(
    args: list[str], code: int
) -> None:
    @command("pick", dependencies=[dependency.requires("x", "other")])
    @argument("x")
    @flag("other")
    def pick(x: str = "default", *, other: bool = False) -> None:
        _ = (x, other)

    assert run(pick, args).returncode == code


@pytest.mark.parametrize(
    ("args", "code"),
    [(["-vv"], 2), ([], 0)],
    ids=["given", "missing"],
)
def test_a_counting_flag_counts_as_given_when_passed(
    args: list[str], code: int
) -> None:
    @command("pick", dependencies=[dependency.requires("verbose", "other")])
    @flag("verbose", "-v")
    @flag("other")
    def pick(*, verbose: int = 0, other: bool = False) -> None:
        _ = (verbose, other)

    assert run(pick, args).returncode == code


@pytest.mark.parametrize(
    ("environment", "code"),
    [({"X": "1"}, 2), ({"X": ""}, 0), ({}, 0)],
    ids=["set", "empty", "unset"],
)
def test_an_env_input_counts_as_given_when_set(
    environment: dict[str, str], code: int
) -> None:
    @command("pick", dependencies=[dependency.requires("x", "other")])
    @env("x")
    @flag("other")
    def pick(x: str = "default", *, other: bool = False) -> None:
        _ = (x, other)

    result = run(pick, [], env=environment)

    assert result.returncode == code


@pytest.mark.parametrize(
    ("text", "code"),
    [("data", 2), ("", 2), (None, 0)],
    ids=["piped", "empty", "nothing"],
)
def test_stdin_counts_as_given_when_anything_was_piped(
    text: str | None, code: int
) -> None:
    @command("pick", dependencies=[dependency.requires("x", "other")])
    @stdin("x")
    @flag("other")
    def pick(x: str = "default", *, other: bool = False) -> None:
        _ = (x, other)

    assert run(pick, [], input=text).returncode == code


def test_a_failed_conversion_still_counts_as_given() -> None:
    @command("pick", dependencies=[dependency.requires("count", "other")])
    @option("count")
    @flag("other")
    def pick(count: int = 1, *, other: bool = False) -> None:
        _ = (count, other)

    result = run(pick, ["--count", "x"])

    assert result.stderr == (
        "error: --count: 'x' isn't a whole number.\n"
        "error: --count requires --other.\n"
        "Run 'pick --help' for usage.\n"
    )


@pytest.mark.parametrize(
    ("args", "text", "code"),
    [(["--x", "--other"], None, 2), (["--x"], "piped", 2), (["--x"], None, 0)],
    ids=["typed", "piped", "alone"],
)
def test_alone_counts_typed_and_piped_inputs_but_not_env(
    args: list[str], text: str | None, code: int
) -> None:
    @command("pick", dependencies=[dependency.alone("x")])
    @flag("x")
    @flag("other")
    @env("token")
    @stdin("data")
    def pick(
        token: str = "", data: str = "", *, x: bool = False, other: bool = False
    ) -> None:
        _ = (token, data, x, other)

    result = run(pick, args, env={"TOKEN": "secret"}, input=text)

    assert result.returncode == code


def test_a_group_checks_its_own_dependencies() -> None:
    @group("notes", dependencies=[dependency.conflicts("quiet", "verbose")])
    @flag("quiet", "-q")
    @flag("verbose", "-v")
    def notes(*, quiet: bool = False, verbose: bool = False) -> None:
        _ = (quiet, verbose)

    @command("list")
    def list_notes() -> None: ...

    notes.add(list_notes)

    result = run(notes, ["-qv", "list"])

    assert result.stderr == (
        "error: --quiet can't be used with --verbose.\n"
        "Run 'notes list --help' for usage.\n"
    )


def test_dependency_errors_come_after_input_errors_and_before_misplaced_words() -> None:
    @command(
        "pick",
        dependencies=[dependency.requires("a", "b"), dependency.conflicts("a", "c")],
    )
    @option("count")
    @flag("a")
    @flag("b")
    @flag("c")
    def pick(
        count: int = 1, *, a: bool = False, b: bool = False, c: bool = False
    ) -> None:
        _ = (count, a, b, c)

    result = run(pick, ["--count", "x", "--a", "--c", "extra"])

    assert result.stderr == (
        "error: --count: 'x' isn't a whole number.\n"
        "error: --a requires --b.\n"
        "error: --a can't be used with --c.\n"
        "error: unexpected argument 'extra'.\n"
        "Run 'pick --help' for usage.\n"
    )


def test_help_doesnt_check_dependencies() -> None:
    @command("pick", dependencies=[dependency.at_least(1, "a", "b")])
    @flag("a")
    @flag("b")
    def pick(*, a: bool = False, b: bool = False) -> None:
        _ = (a, b)

    assert run(pick, ["--help"]).returncode == 0


@pytest.mark.parametrize(
    ("make", "arguments", "message"),
    [
        (
            dependency.requires,
            ("otp", 1),
            (
                "dependency.requires takes the names of inputs as strings, "
                'such as "user", not 1.'
            ),
        ),
        (
            dependency.at_most,
            ("1", "a", "b"),
            "dependency.at_most takes the count as an int, such as 1, not '1'.",
        ),
        (
            dependency.exactly,
            (True, "a", "b"),
            "dependency.exactly takes the count as an int, such as 1, not True.",
        ),
    ],
    ids=["name", "count", "bool count"],
)
def test_dependency_rejects_the_wrong_types(
    make: Callable[..., object], arguments: tuple[object, ...], message: str
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = make(*arguments)


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (
            lambda: dependency.at_least(0, "a", "b"),
            (
                'dependency.at_least(0, "a", "b") needs none of them, so it changes '
                "nothing. Use a count from 1 to 1."
            ),
        ),
        (
            lambda: dependency.at_least(3, "a", "b", "c"),
            (
                'dependency.at_least(3, "a", "b", "c") needs all of them, '
                "so every one of them is always given. Use a count from 1 to 2."
            ),
        ),
        (
            lambda: dependency.at_most(0, "a", "b"),
            (
                'dependency.at_most(0, "a", "b") allows none of them, '
                "so none of them can be given. Use a count from 1 to 1."
            ),
        ),
        (
            lambda: dependency.at_most(2, "a", "b"),
            (
                'dependency.at_most(2, "a", "b") allows all of them, so it changes '
                "nothing. Use a count from 1 to 1."
            ),
        ),
        (
            lambda: dependency.exactly(2, "a", "b"),
            (
                'dependency.exactly(2, "a", "b") needs all of them, '
                "so every one of them is always given. Use a count from 1 to 1."
            ),
        ),
        (
            lambda: dependency.together("user", "user"),
            'dependency.together("user", "user") names \'user\' twice. Remove one.',
        ),
        (
            lambda: dependency.at_most(1, "a", "a", "b"),
            'dependency.at_most(1, "a", "a", "b") names \'a\' twice. Remove one.',
        ),
    ],
)
def test_dependency_rejects_counts_and_names_that_change_nothing(
    make: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=exactly(message)):
        _ = make()


@pytest.mark.parametrize("decorator", [command])
@pytest.mark.parametrize(
    ("value", "shown"),
    [(dependency.together("a", "b"), 'dependency.together("a", "b")'), ("a", "'a'")],
    ids=["one dependency", "str"],
)
def test_dependencies_must_be_a_list(
    decorator: Callable[..., object], value: object, shown: str
) -> None:
    message = (
        "@command takes dependencies as a list, such as "
        f'dependencies=[dependency.together("user", "password")], not {shown}.'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = decorator("pick", dependencies=value)


@pytest.mark.parametrize("decorator", [group])
def test_dependencies_must_be_made_with_dependency(
    decorator: Callable[..., object],
) -> None:
    message = (
        "@group takes dependencies made with dependency, such as "
        'dependency.together("user", "password"), not \'a\'.'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = decorator("notes", dependencies=["a"])


@pytest.mark.parametrize(
    ("name", "suggestion"),
    [("usr", " Did you mean 'user'?"), ("zzz", "")],
    ids=["close", "far"],
)
def test_dependency_rejects_an_unknown_name(name: str, suggestion: str) -> None:
    def connect(user: str | None = None, otp: str | None = None) -> None:
        _ = (user, otp)

    decorated = option("user")(option("otp")(connect))
    message = (
        f'dependency.requires("otp", "{name}") names {name!r}, which isn\'t an '
        f"input of command 'connect'.{suggestion}"
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("connect", dependencies=[dependency.requires("otp", name)])(
            decorated
        )


@CHECKS
def test_dependency_rejects_an_input_without_a_default(check: Check) -> None:
    @command("pick", dependencies=[dependency.requires("otp", "user")])
    @option("otp")
    @option("user")
    def pick(user: str, otp: str | None = None) -> None:
        _ = (user, otp)

    message = (
        'dependency.requires("otp", "user") names \'user\', which has no default, '
        "so it is always given. Give it one, such as user: str | None = None, "
        "or remove the dependency."
    )
    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(pick)


def test_an_optional_type_without_a_default_keeps_one_none_in_the_fix() -> None:
    @command("pick", dependencies=[dependency.requires("otp", "user")])
    @option("otp")
    @option("user")
    def pick(user: str | None, otp: str | None = None) -> None:
        _ = (user, otp)

    message = (
        'dependency.requires("otp", "user") names \'user\', which has no default, '
        "so it is always given. Give it one, such as user: str | None = None, "
        "or remove the dependency."
    )
    with pytest.raises(ValueError, match=exactly(message)):
        validate(pick)


CYCLES = {
    "two": (
        [dependency.requires("a", "b"), dependency.requires("b", "a")],
        ('--a and --b require each other. Use dependency.together("a", "b") instead.'),
    ),
    "three": (
        [
            dependency.requires("a", "b"),
            dependency.requires("b", "c"),
            dependency.requires("c", "a"),
        ],
        (
            "--a, --b and --c require each other in a cycle. "
            'Use dependency.together("a", "b", "c") instead.'
        ),
    ),
    "past the first": (
        [
            dependency.requires("a", "b"),
            dependency.requires("b", "c"),
            dependency.requires("c", "b"),
        ],
        ('--b and --c require each other. Use dependency.together("b", "c") instead.'),
    ),
}


@CHECKS
@pytest.mark.parametrize("case", CYCLES)
def test_dependency_rejects_a_requires_cycle(check: Check, case: str) -> None:
    dependencies, message = CYCLES[case]

    @command("pick", dependencies=dependencies)
    @flag("a")
    @flag("b")
    @flag("c")
    def pick(*, a: bool = False, b: bool = False, c: bool = False) -> None:
        _ = (a, b, c)

    with pytest.raises(ValueError, match=exactly(message)):
        _ = check(pick)


VALIDATED = {
    "never met": (
        [dependency.exactly(1, "a", "b"), dependency.together("a", "b")],
        (
            'these dependencies can never all be met: dependency.exactly(1, "a", "b") '
            'and dependency.together("a", "b"). Change one of them.'
        ),
    ),
    "never given": (
        [
            dependency.together("a", "b"),
            dependency.together("a", "c"),
            dependency.at_most(1, "b", "c"),
        ],
        (
            "--a, --b and --c can never be given, because these dependencies "
            'contradict each other: dependency.together("a", "b"), '
            'dependency.together("a", "c") and dependency.at_most(1, "b", "c"). '
            "Change one of them."
        ),
    ),
    "never given alone": (
        [dependency.alone("a"), dependency.requires("a", "b")],
        (
            "--a can never be given, because these dependencies contradict each other: "
            'dependency.alone("a") and dependency.requires("a", "b"). '
            "Change one of them."
        ),
    ),
    "implied by requires": (
        [dependency.requires_any("a", "b", "c"), dependency.requires("a", "b")],
        (
            'dependency.requires_any("a", "b", "c") is already implied by '
            'dependency.requires("a", "b"). Remove it.'
        ),
    ),
    "redundant": (
        [dependency.at_most(1, "a", "b"), dependency.conflicts("a", "b")],
        (
            'dependency.at_most(1, "a", "b") is already implied by '
            'dependency.conflicts("a", "b"). Remove it.'
        ),
    ),
}


@pytest.mark.parametrize("case", VALIDATED)
def test_validate_rejects_dependencies_that_contradict_or_repeat(case: str) -> None:
    dependencies, message = VALIDATED[case]

    @command("pick", dependencies=dependencies)
    @flag("a")
    @flag("b")
    @flag("c")
    def pick(*, a: bool = False, b: bool = False, c: bool = False) -> None:
        _ = (a, b, c)

    with pytest.raises(ValueError, match=exactly(message)) as info:
        validate(pick)

    assert run(pick, ["--help"]).returncode == 0
    assert info.value.__notes__[0].startswith("in command 'pick', defined at ")


def test_validate_checks_each_group_of_related_inputs_alone() -> None:
    @command(
        "pick",
        dependencies=[
            dependency.together("a", "b"),
            dependency.at_most(1, "c", "d"),
        ],
    )
    @flag("a")
    @flag("b")
    @flag("c")
    @flag("d")
    @env("token")
    def pick(
        token: str = "",
        *,
        a: bool = False,
        b: bool = False,
        c: bool = False,
        d: bool = False,
    ) -> None:
        _ = (token, a, b, c, d)

    validate(pick)
