import getpass
import io
import re
import sys
from typing import TYPE_CHECKING, cast

import pytest

from cliron import argument, between, command, fallback, option, stdin
from cliron.testing import run, validate

if TYPE_CHECKING:
    from collections.abc import Callable


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@command("login")
@option("user")
@fallback(prompt=True)
@option("api_token")
@fallback(env="API_TOKEN")
@fallback(prompt="Paste your token:", hidden=True)
def login(user: str, api_token: str) -> str:
    return f"{user} {api_token}"


@command("serve")
@option("port")
@fallback(prompt=True)
@between(1, 65535)
@option("host")
@fallback(prompt=True)
def serve(port: int = 8080, host: str = "localhost") -> str:
    return f"{host}:{port}"


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_a_prompt_asks_at_a_terminal() -> None:
    result = run(login, [], input="ada\nsecret\n", terminal=True, env={})

    assert result.stdout == "ada secret\n"
    assert result.stderr == "User: Paste your token: "
    assert result.returncode == 0


def test_a_prompt_only_asks_for_what_has_no_value() -> None:
    result = run(
        login,
        ["--user", "ada"],
        input="ignored\n",
        terminal=True,
        env={"API_TOKEN": "t"},
    )

    assert result.stdout == "ada t\n"
    assert result.stderr == ""


def test_without_a_terminal_nothing_is_asked() -> None:
    result = run(login, [], input="ada\nsecret\n", env={})

    assert result.returncode == 2
    assert result.stderr == (
        "error: --user is required.\n"
        "error: --api-token is required. It can also come from $API_TOKEN.\n"
        "Run 'login --help' for usage.\n"
    )


@pytest.mark.parametrize("answers", ["\n\n", ""])
def test_an_empty_answer_or_the_end_of_input_gives_no_text(answers: str) -> None:
    result = run(serve, [], input=answers, terminal=True)

    assert result.stdout == "localhost:8080\n"
    assert result.stderr == "Port: Host: "


@pytest.mark.parametrize("answers", ["ada\n", "ada\n\n"])
def test_a_hidden_prompt_without_an_answer_gives_no_text(answers: str) -> None:
    result = run(login, [], input=answers, terminal=True, env={"API_TOKEN": ""})

    assert result.returncode == 2
    assert result.stderr.startswith(
        "User: Paste your token: error: --api-token is required."
    )


def test_an_answer_is_converted_and_checked_once() -> None:
    result = run(serve, [], input="99999\nexample.com\n", terminal=True)

    assert result.returncode == 2
    assert result.stderr == (
        "Port: error: --port: 99999 isn't between 1 and 65535.\n"
        "Run 'serve --help' for usage.\n"
    )


def test_nothing_is_asked_once_the_command_line_has_errors() -> None:
    result = run(serve, ["--nope"], input="80\nexample.com\n", terminal=True)

    assert result.stderr.startswith("error: unknown option '--nope'.")
    assert "Port:" not in result.stderr


def test_nothing_is_asked_after_a_value_that_isnt_valid() -> None:
    result = run(serve, ["--port", "abc"], input="example.com\n", terminal=True)

    assert result.stderr == (
        "error: --port: 'abc' isn't a whole number.\nRun 'serve --help' for usage.\n"
    )


def test_the_default_question_comes_from_the_name() -> None:
    @command("copy")
    @argument("from_")
    @fallback(prompt=True)
    def copy(from_: str) -> str:
        return from_

    result = run(copy, [], input="here\n", terminal=True)

    assert result.stdout == "here\n"
    assert result.stderr == "From: "


def test_stdin_at_a_terminal_reads_nothing() -> None:
    @command("say")
    @stdin("text")
    @fallback(prompt="Say what?")
    def say(text: str) -> str:
        return text

    result = run(say, [], input="hello\n", terminal=True)

    assert result.stdout == "hello\n"
    assert result.stderr == "Say what? "


def test_a_hidden_prompt_uses_getpass_at_the_real_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def fake_getpass(prompt: str, stream: object = None) -> str:
        _ = stream
        asked.append(prompt)
        return "secret"

    terminal = Terminal("ada\n")
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", terminal)
    monkeypatch.setattr(sys, "__stdin__", terminal)
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "argv", ["login"])
    monkeypatch.setattr(getpass, "getpass", fake_getpass)
    monkeypatch.delenv("API_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exit_:
        login()

    assert exit_.value.code == 0
    assert asked == ["Paste your token: "]
    assert output.getvalue() == "ada secret\n"


@pytest.mark.parametrize(
    ("options", "error", "message"),
    [
        *(
            (
                {"prompt": prompt},
                error,
                (
                    "@fallback takes prompt as True or a question, such as "
                    f'prompt="Which region?", not {prompt!r}.'
                ),
            )
            for prompt, error in [
                ("", ValueError),
                (" ", ValueError),
                (False, TypeError),
                (3, TypeError),
            ]
        ),
        (
            {"prompt": True, "hidden": 1},
            TypeError,
            "@fallback takes hidden as True or False, not 1.",
        ),
        (
            {"env": "TOKEN", "hidden": True},
            TypeError,
            (
                "@fallback takes hidden only with prompt, such as "
                "@fallback(prompt=True, hidden=True)."
            ),
        ),
        (
            {"env": "TOKEN", "prompt": True},
            TypeError,
            (
                "@fallback takes one source, but got env and prompt. "
                "Put each in its own @fallback."
            ),
        ),
    ],
)
def test_fallback_checks_its_prompt(
    options: dict[str, object], error: type[Exception], message: str
) -> None:
    make = cast("Callable[..., object]", fallback)

    with pytest.raises(error, match=exactly(message)):
        _ = make(**options)


def test_a_misplaced_prompt_is_named_as_written() -> None:
    @option("port")
    @between(1, 65535)
    @fallback(prompt="Port?", hidden=True)
    def serve(port: int = 80) -> None:
        _ = port

    message = (
        '@fallback(prompt="Port?", hidden=True) is below @between(1, 65535), but '
        "fallbacks come before children. Move it above @between(1, 65535)."
    )
    with pytest.raises(TypeError, match=exactly(message)):
        validate(command("serve")(serve))
