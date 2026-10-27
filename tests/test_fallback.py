import asyncio
import re
from collections.abc import Callable
from datetime import date
from typing import cast

import pytest

from cliron import (
    argument,
    between,
    child,
    command,
    dependency,
    env,
    fallback,
    flag,
    hook,
    length,
    on,
    option,
    parent,
    stdin,
)
from cliron.testing import run, validate


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def saved_port(name: str) -> str | None:
    return "4000" if name == "port" else None


def nothing(name: str) -> str | None:
    _ = name
    return None


async def remote(name: str) -> str | None:
    await asyncio.sleep(0)
    return f"remote {name}"


def number(name: str) -> object:
    return len(name)


def locked(name: str) -> str | None:
    message = f"the keyring is locked, so there is no {name}"
    raise PermissionError(message)


def pair(name: str, other: str) -> str | None:
    return f"{name} {other}"


def anonymous(exc: PermissionError) -> str:
    _ = exc
    return "anonymous"


def port_80(exc: ValueError) -> int:
    _ = exc
    return 80


@parent
def git_branch(name: str) -> str | None:
    return f"main for {name}"


@child
def us_date(text: str) -> date:
    month, day, year = text.split("/")
    return date(int(year), int(month), int(day))


@command("serve")
@option("port", help="The port.")
@fallback(env="PORT")
@fallback(env="DEFAULT_PORT")
@between(1, 65535)
def serve(port: int = 8080) -> str:
    return f"port {port}"


@pytest.mark.parametrize(
    ("args", "variables", "output"),
    [
        (["--port", "1"], {"PORT": "2", "DEFAULT_PORT": "3"}, "port 1\n"),
        ([], {"PORT": "2", "DEFAULT_PORT": "3"}, "port 2\n"),
        ([], {"DEFAULT_PORT": "3"}, "port 3\n"),
        ([], {"PORT": "", "DEFAULT_PORT": "3"}, "port 3\n"),
        ([], {}, "port 8080\n"),
    ],
)
def test_the_parent_comes_first_then_each_fallback_then_the_default(
    args: list[str], variables: dict[str, str], output: str
) -> None:
    result = run(serve, args, env=variables)

    assert result.stdout == output
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("variables", "error"),
    [
        ({"PORT": "abc"}, "$PORT: 'abc' isn't a whole number."),
        ({"DEFAULT_PORT": "99999"}, "$DEFAULT_PORT: 99999 isn't between 1 and 65535."),
    ],
)
def test_a_fallback_is_converted_and_checked_like_the_parent(
    variables: dict[str, str], error: str
) -> None:
    result = run(serve, [], env=variables)

    assert result.returncode == 2
    assert result.stderr == f"error: {error}\nRun 'serve --help' for usage.\n"


def test_a_first_child_that_takes_text_converts_a_fallback_too() -> None:
    @command("remind")
    @option("when")
    @fallback(env="WHEN")
    @us_date()
    def remind(when: date) -> str:
        return when.isoformat()

    assert run(remind, [], env={"WHEN": "10/27/2026"}).stdout == "2026-10-27\n"


def test_a_function_fallback_gets_the_name_and_may_be_async() -> None:
    @command("deploy")
    @option("token")
    @fallback(fn=nothing)
    @fallback(fn=remote)
    def deploy(token: str) -> str:
        return token

    assert run(deploy, []).stdout == "remote token\n"


def test_a_parent_function_can_be_a_fallback_too() -> None:
    @command("deploy")
    @option("branch")
    @fallback(fn=git_branch)
    @git_branch("base")
    def deploy(branch: str, base: str) -> str:
        return f"{branch}, onto {base}"

    assert run(deploy, []).stdout == "main for branch, onto main for base\n"


def test_a_parent_function_is_named_like_a_plain_one() -> None:
    @option("branch")
    @length(1)
    @fallback(fn=git_branch)
    def deploy(branch: str) -> None:
        _ = branch

    message = (
        "@fallback(fn=git_branch) is below @length(low=1), but fallbacks come "
        "before children. Move it above @length(low=1)."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("deploy")(deploy)


def test_text_from_a_function_is_named_by_the_parent() -> None:
    @command("serve")
    @option("port")
    @fallback(fn=saved_port)
    @between(1, 1024)
    def serve(port: int) -> str:
        return f"port {port}"

    result = run(serve, [])

    assert result.stderr == (
        "error: --port: 4000 isn't between 1 and 1024.\nRun 'serve --help' for usage.\n"
    )


def test_a_missing_value_names_the_variables() -> None:
    @command("deploy")
    @option("token")
    @fallback(env="API_TOKEN")
    @fallback(fn=nothing)
    @fallback(env="TOKEN")
    def deploy(token: str) -> str:
        return token

    result = run(deploy, [], env={})

    assert result.returncode == 2
    assert result.stderr == (
        "error: --token is required. It can also come from $API_TOKEN or $TOKEN.\n"
        "Run 'deploy --help' for usage.\n"
    )


def test_other_parents_can_fall_back_too() -> None:
    @command("say")
    @env("voice", variable="SAY_VOICE")
    @fallback(env="VOICE")
    @stdin("text")
    @fallback(env="TEXT")
    def say(voice: str, text: str) -> str:
        return f"{voice}: {text}"

    result = run(say, [], env={"VOICE": "robot", "TEXT": "hi"})

    assert result.stdout == "robot: hi\n"


def test_missing_piped_input_names_the_variable_before_the_example() -> None:
    @command("say")
    @stdin("text")
    @fallback(env="TEXT")
    def say(text: str) -> str:
        return text

    assert run(say, [], env={}).stderr == (
        "error: stdin: nothing was piped in. It can also come from $TEXT. "
        "For example: cat file.txt | say\n"
        "Run 'say --help' for usage.\n"
    )


def test_an_argument_with_a_fallback_can_be_left_out() -> None:
    @command("login")
    @argument("token")
    @fallback(env="TOKEN")
    def login(token: str) -> str:
        return token

    assert run(login, ["typed"], env={"TOKEN": "set"}).stdout == "typed\n"
    assert run(login, [], env={"TOKEN": "set"}).stdout == "set\n"
    assert run(login, ["--help"]).stdout.startswith("Usage: login [OPTIONS] [TOKEN]\n")


def test_an_argument_with_a_fallback_counts_as_optional_for_the_order() -> None:
    @argument("token")
    @fallback(env="TOKEN")
    @argument("user")
    def login(token: str, user: str) -> None:
        _ = (token, user)

    message = (
        "argument 'user' has no default, so it can't come after argument 'token', "
        "which has a fallback. Give 'user' a default, or move its @argument above "
        "'token'."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        validate(command("login")(login))


def test_arguments_that_all_have_fallbacks_can_follow_each_other() -> None:
    @command("login")
    @argument("token")
    @fallback(env="TOKEN")
    @argument("user")
    @fallback(env="USER")
    def login(token: str, user: str) -> str:
        return f"{user} {token}"

    validate(login)
    assert run(login, ["t"], env={"USER": "ada"}).stdout == "ada t\n"


def test_help_shows_the_variables_before_the_children() -> None:
    @command("serve")
    @option("port", help="The port.")
    @fallback(env="PORT")
    @fallback(fn=saved_port)
    @fallback(env="DEFAULT_PORT")
    @between(1, 65535)
    def serve(port: int = 8080) -> None:
        _ = port

    assert run(serve, ["--help"]).stdout == (
        "Usage: serve [OPTIONS]\n"
        "\n"
        "Options:\n"
        "  --port INT  The port. Falls back to $PORT, then $DEFAULT_PORT. 1 to 65535.\n"
        "              (default: 8080)\n"
        "  -h, --help  Show this help and exit.\n"
    )


def test_an_error_hook_below_a_fallback_belongs_to_the_parent() -> None:
    @command("show")
    @option("user")
    @fallback(fn=locked)
    @hook(on.error(), anonymous)
    def show(user: str) -> str:
        return user

    assert run(show, []).stdout == "anonymous\n"


def test_an_error_hook_handles_a_bad_fallback_value() -> None:
    @command("serve")
    @option("port")
    @hook(on.error(), port_80)
    @fallback(env="PORT")
    @between(1, 65535)
    def serve(port: int) -> str:
        return f"port {port}"

    assert run(serve, [], env={"PORT": "abc"}).stdout == "port 80\n"


def test_an_error_in_a_function_fallback_is_raised_as_it_is() -> None:
    @command("show")
    @option("user")
    @fallback(fn=locked)
    def show(user: str) -> str:
        return user

    with pytest.raises(
        PermissionError, match="the keyring is locked, so there is no user"
    ):
        _ = run(show, [])


def test_a_function_fallback_must_return_text() -> None:
    @command("show")
    @option("user")
    @fallback(fn=cast("Callable[[str], str | None]", number))
    def show(user: str) -> str:
        return user

    message = "@fallback(fn=number) returned int. Make it return str or None."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(show, [])


def test_a_fallback_value_counts_as_given() -> None:
    @command("deploy", dependencies=[dependency.requires("token", "user")])
    @option("token")
    @fallback(env="TOKEN")
    @option("user")
    def deploy(token: str | None = None, user: str | None = None) -> str:
        return f"{user} {token}"

    result = run(deploy, [], env={"TOKEN": "t"})

    assert result.returncode == 2
    assert result.stderr.startswith("error: --token requires --user.\n")


def test_alone_ignores_a_fallback_value() -> None:
    @command("tool", dependencies=[dependency.alone("check")])
    @flag("check")
    @option("token")
    @fallback(env="TOKEN")
    def tool(*, check: bool = False, token: str | None = None) -> str:
        return f"{check} {token}"

    assert run(tool, ["--check"], env={"TOKEN": "t"}).stdout == "True t\n"
    assert run(tool, ["--check", "--token", "t"]).returncode == 2


def test_a_fallback_after_another_parents_children_belongs_to_the_next_parent() -> None:
    @command("serve")
    @option("port")
    @between(1, 65535)
    @option("host")
    @fallback(env="HOST")
    def serve(port: int = 80, host: str = "localhost") -> str:
        return f"{host}:{port}"

    assert run(serve, [], env={"HOST": "example.com"}).stdout == "example.com:80\n"


def test_a_fallback_below_a_child_is_a_mistake() -> None:
    @option("port")
    @between(1, 65535)
    @between(high=1024)
    @fallback(env="PORT")
    def serve(port: int = 80) -> None:
        _ = port

    message = (
        '@fallback(env="PORT") is below @between(1, 65535), but fallbacks come '
        "before children. Move it above @between(1, 65535)."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("serve")(serve)


def test_a_fallback_above_every_parent_is_a_mistake() -> None:
    @fallback(env="PORT")
    @option("port")
    def serve(port: int = 80) -> None:
        _ = port

    message = (
        '@fallback(env="PORT") is above every parent, so it has nothing to fall '
        "back for. Put it right below the parent whose value it gives."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("serve")(serve)


def test_a_flag_cant_have_a_fallback() -> None:
    @flag("verbose")
    @fallback(env="VERBOSE")
    def show(*, verbose: bool = False) -> None:
        _ = verbose

    message = (
        '@flag("verbose") can\'t have a fallback, because a flag has no text. '
        'Remove @fallback(env="VERBOSE").'
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = command("show")(show)


def test_a_fallback_must_decorate_a_function() -> None:
    message = (
        '@fallback(env="PORT") must decorate a function, '
        "so it goes below @command or @group."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        _ = fallback(env="PORT")(cast("Callable[..., object]", 3))


@pytest.mark.parametrize(
    ("options", "error", "message"),
    [
        (
            {},
            TypeError,
            (
                '@fallback takes one source, such as @fallback(env="API_TOKEN") '
                "or @fallback(fn=git_branch)."
            ),
        ),
        (
            {"env": "PORT", "fn": saved_port},
            TypeError,
            (
                "@fallback takes one source, but got both env and fn. "
                "Put each in its own @fallback."
            ),
        ),
        (
            {"env": 3},
            TypeError,
            '@fallback takes env as a string, such as env="GITHUB_TOKEN", not 3.',
        ),
        (
            {"env": "1PORT"},
            ValueError,
            (
                "'1PORT' isn't an environment variable name. Use letters, digits "
                "and underscores, not starting with a digit, such as 'GITHUB_TOKEN'."
            ),
        ),
        (
            {"fn": 3},
            TypeError,
            (
                "@fallback takes fn as a function, such as "
                "def git_branch(name: str) -> str | None, not 3."
            ),
        ),
        (
            {"fn": pair},
            TypeError,
            (
                "fallback function 'pair' must take the name as its only argument, "
                "such as def pair(name: str) -> str | None."
            ),
        ),
    ],
)
def test_fallback_checks_what_it_is_given(
    options: dict[str, object], error: type[Exception], message: str
) -> None:
    make = cast("Callable[..., object]", fallback)

    with pytest.raises(error, match=exactly(message)):
        _ = make(**options)


def test_a_fallback_reads_one_value() -> None:
    @command("tag")
    @option("label")
    @fallback(env="LABELS")
    def tag(label: list[str]) -> None:
        _ = label

    message = (
        "parameter 'label' has the type list[str], but @fallback(env=\"LABELS\") "
        "reads one value. Use a type without list or tuple."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        validate(tag)


@pytest.mark.parametrize(
    ("second", "message"),
    [
        (
            env("other", variable="PORT"),
            (
                '$PORT is used by both @fallback(env="PORT") below @option("port") '
                'and @env("other"). Give one of them another variable.'
            ),
        ),
        (
            option("other"),
            (
                '$PORT is used by both @fallback(env="PORT") below @option("port") '
                'and @fallback(env="PORT") below @option("other"). '
                "Give one of them another variable."
            ),
        ),
    ],
)
def test_two_inputs_cant_read_the_same_variable(
    second: Callable[[Callable[..., object]], Callable[..., object]], message: str
) -> None:
    @option("port")
    @fallback(env="PORT")
    @second
    @fallback(env="PORT")
    def serve(port: int = 80, other: str = "") -> None:
        _ = (port, other)

    with pytest.raises(ValueError, match=exactly(message)):
        _ = command("serve")(serve)
