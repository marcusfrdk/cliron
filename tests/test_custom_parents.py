import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from cliron import (
    Parent,
    argument,
    between,
    command,
    dependency,
    env,
    flag,
    group,
    option,
    parent,
    stdin,
)
from cliron.testing import run, validate

SECRETS = {"api_key": "1234", "retries": "9"}
BRANCHES = {"branch": "main"}
NOT_TEXT: object = 5


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


class Secret(Parent):
    def load(self) -> str | None:
        return SECRETS.get(self.name)


class DotEnv(Parent):
    def __init__(self, name: str, *, path: Path, help: str | None = None) -> None:
        super().__init__(name, help=help)
        self.path: Path = path

    def load(self) -> str | None:
        variable = self.name.upper()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key == variable:
                return value
        return None

    def label(self) -> str:
        return f"${self.name.upper()}"

    def missing(self) -> str:
        return f"{self.label()} isn't in {self.path.name}."


class Broken(Parent):
    def load(self) -> str | None:
        return cast("str", NOT_TEXT)


@parent
def git_branch(name: str) -> str | None:
    return BRANCHES.get(name)


def nothing() -> str | None:
    return None


def two(name: str, other: str) -> str | None:
    return name + other


def test_a_parent_fills_its_parameter_from_what_it_loads() -> None:
    @command("weather")
    @Secret("api_key", help="Key for the weather service.")
    def weather(api_key: str) -> str:
        return f"Using {api_key}"

    assert run(weather, []).stdout == "Using 1234\n"


def test_what_a_parent_loads_is_converted_and_checked() -> None:
    @command("fetch")
    @Secret("retries")
    @between(1, 5)
    def fetch(retries: int) -> int:
        return retries

    assert run(fetch, []).stderr == (
        "error: retries: 9 isn't between 1 and 5.\nRun 'fetch --help' for usage.\n"
    )


def test_a_parent_that_loads_nothing_uses_the_default_or_is_missing() -> None:
    @command("deploy")
    @Secret("region")
    @Secret("token")
    def deploy(token: str, region: str = "eu") -> str:
        return f"{region} {token}"

    assert run(deploy, []).stderr == (
        "error: token is required.\nRun 'deploy --help' for usage.\n"
    )


def test_a_parent_can_take_options_and_name_itself(tmp_path: Path) -> None:
    found = tmp_path / ".env"
    _ = found.write_text("API_KEY=abcd\nRETRIES=x\n", encoding="utf-8")

    @command("weather")
    @DotEnv("api_key", path=found)
    @DotEnv("retries", path=found)
    @DotEnv("region", path=found)
    def weather(api_key: str, retries: int, region: str) -> str:
        return f"{api_key} {retries} {region}"

    assert run(weather, []).stderr == (
        "error: $RETRIES: 'x' isn't a whole number.\n"
        "error: $REGION isn't in .env.\n"
        "Run 'weather --help' for usage.\n"
    )


def test_a_function_can_be_a_parent() -> None:
    @command("deploy")
    @git_branch("branch", help="The branch to deploy.")
    def deploy(branch: str) -> str:
        return f"Deploying {branch}"

    assert run(deploy, []).stdout == "Deploying main\n"


def test_help_lists_parents_under_input() -> None:
    @command("deploy")
    @git_branch("branch", help="The branch to deploy.")
    @Secret("token", help="An access token.")
    @stdin("notes", help="Release notes.")
    def deploy(branch: str, notes: str, token: str | None = None) -> str:
        return f"{branch} {notes} {token}"

    expected = (
        "Input:\n"
        "  branch      The branch to deploy. (required)\n"
        "  token       An access token.\n"
        "  stdin       Release notes. (required)\n"
    )
    assert run(deploy, ["--help"]).stdout.endswith(expected)


def test_a_group_can_have_a_parent() -> None:
    seen: list[str] = []

    @group("notes")
    @Secret("api_key", help="Key for the notes service.")
    def notes(api_key: str) -> None:
        seen.append(api_key)

    @command("add")
    def add() -> str:
        return "Added."

    notes.add(add)

    assert run(notes, ["add"]).stdout == "Added.\n"
    assert seen == ["1234"]
    assert run(notes, ["add", "--help"]).stdout.endswith(
        "Input:\n  api_key     Key for the notes service. (required)\n"
    )


def test_a_parent_that_loads_text_counts_as_given() -> None:
    @command("connect", dependencies=[dependency.exactly(1, "api_key", "user")])
    @Secret("api_key")
    @option("user", "-u")
    def connect(api_key: str | None = None, user: str | None = None) -> str:
        return f"{api_key} {user}"

    assert run(connect, ["-u", "ada"]).stderr == (
        "error: exactly 1 of api_key and -u/--user must be given, but both were.\n"
        "Run 'connect --help' for usage.\n"
    )


@pytest.mark.parametrize(
    "found",
    [
        argument("name"),
        option("name"),
        flag("name"),
        env("name"),
        stdin("name"),
        Secret("name"),
        git_branch("name"),
    ],
    ids=["argument", "option", "flag", "env", "stdin", "class", "function"],
)
def test_every_parent_is_a_parent(found: object) -> None:
    assert isinstance(found, Parent)


def test_a_parent_must_load_text() -> None:
    @command("pick")
    @Broken("count")
    def pick(count: int = 1) -> int:
        return count

    message = '@Broken("count") returned int from load(). Make it return str or None.'
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(pick, [])


def test_a_parent_fills_one_value() -> None:
    @command("tag")
    @Secret("tags")
    def tag(tags: list[str]) -> int:
        return len(tags)

    message = (
        "parameter 'tags' has the type list[str], but @Secret(\"tags\") reads one "
        "value. Use a type without list or tuple."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        validate(tag)


@pytest.mark.parametrize(
    ("make", "arguments", "keywords", "message"),
    [
        (Secret, ("API_KEY",), {}, "'API_KEY' isn't snake_case. Use 'api_key'."),
        (
            Secret,
            (nothing,),
            {},
            '@Secret needs a name in parentheses, such as @Secret("name").',
        ),
        (
            Secret,
            ("api_key",),
            {"help": 3},
            '@Secret takes help as a string, such as help="How many.", not 3.',
        ),
        (
            git_branch,
            (nothing,),
            {},
            '@git_branch needs a name in parentheses, such as @git_branch("name").',
        ),
        (
            Secret("api_key"),
            (42,),
            {},
            "@Secret must decorate a function, so it goes below @command or @group.",
        ),
        (
            parent,
            (42,),
            {},
            (
                "@parent must decorate a function, such as "
                "def git_branch(name: str) -> str | None, not 42."
            ),
        ),
        (
            parent,
            (nothing,),
            {},
            (
                "@parent function 'nothing' must take the name as its only "
                "argument, such as def nothing(name: str) -> str | None."
            ),
        ),
        (
            parent,
            (two,),
            {},
            (
                "@parent function 'two' must take the name as its only argument, "
                "such as def two(name: str) -> str | None."
            ),
        ),
    ],
    ids=[
        "name",
        "no-parentheses",
        "help",
        "function-no-parentheses",
        "above-a-non-function",
        "not-a-function",
        "no-name",
        "two-arguments",
    ],
)
def test_a_wrong_parent_definition_is_rejected(
    make: Callable[..., object],
    arguments: tuple[object, ...],
    keywords: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=exactly(message)):
        _ = make(*arguments, **keywords)
