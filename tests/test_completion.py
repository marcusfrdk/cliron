import os
import pty
import select
import shutil
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Literal

import pytest

from cliron import (
    Parent,
    argument,
    command,
    directory,
    env,
    flag,
    group,
    option,
)
from cliron.testing import run

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX shells")
BASH = shutil.which("bash")
ZSH = shutil.which("zsh")
FISH = shutil.which("fish")
NOTES_DB = Path("notes.db")


class Color(Enum):
    RED = "red"
    DARK_RED = "dark red"


class Locked(Parent):
    def load(self) -> str | None:
        message = "the keyring is locked"
        raise PermissionError(message)


@group("notes", version="1.0")
@flag("quiet", "-q", help="Print nothing but results.")
@env("notes_db", help="Where notes are stored.")
def notes(notes_db: Path = NOTES_DB, *, quiet: bool = False) -> None:
    """Keep notes."""
    _ = (notes_db, quiet)


@command("add")
@argument("text", help="The note.")
@option("tag", "-t", help="A tag to file it under.")
@option("color", help="Don't pick more than one.")
@option("attach", "-a", help="Files to attach, one by one.")
def add(
    text: str,
    tag: str | None = None,
    color: Color = Color.RED,
    attach: tuple[Path, ...] = (),
) -> None:
    """Add a note."""
    _ = (text, tag, color, attach)


@command("list")
@argument("folders", help="Where to look.")
@directory(exists=None)
@option("sort", "-s", help="Sort by name\\size.")
@flag("verbose", "-v", help="Say more.")
def list_notes(
    folders: list[Path],
    sort: Literal["name", "size", "modified"] = "name",
    verbose: int = 0,
) -> None:
    """List notes."""
    _ = (folders, sort, verbose)


@group("tags")
def tags() -> None:
    """Work with tags."""


@command("rename")
def rename() -> None:
    """Rename a tag."""


@command("plain", help_flags=False)
@Locked("secret")
def plain(secret: str = "") -> None:
    """Show nothing."""
    _ = secret


tags.add(rename)
notes.add(add, list_notes, tags, plain)


@pytest.fixture
def place(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _ = (work / "a.txt").write_text("a", encoding="utf-8")
    (work / "docs").mkdir()
    return work


def script(shell: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/notes"])
    result = run(notes, ["--completion", shell])
    assert result.returncode == 0
    path = tmp_path / f"notes.{shell}"
    _ = path.write_text(result.stdout, encoding="utf-8")
    return path


def bash(path: Path, line: str, cwd: Path) -> list[str]:
    assert BASH is not None
    command = (
        'source "$1"; COMP_LINE=$2; COMP_POINT=${#COMP_LINE}; _cliron_notes; '
        'printf "%s\\n" "${COMPREPLY[@]}"'
    )
    result = subprocess.run(
        [BASH, "--noprofile", "--norc", "-c", command, "bash", str(path), line],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stderr == ""
    return sorted(word for word in result.stdout.splitlines() if word)


def fish(path: Path, line: str, cwd: Path) -> list[str]:
    assert FISH is not None
    result = subprocess.run(
        [
            FISH,
            "--no-config",
            "-c",
            "source $argv[1]; complete -C $argv[2]",
            str(path),
            line,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stderr == ""
    return sorted(result.stdout.splitlines())


def zsh(path: Path, typed: str, cwd: Path) -> str:
    assert ZSH is not None
    home = cwd / ".zsh"
    home.mkdir(exist_ok=True)
    lines = [
        f"autoload -Uz compinit && compinit -u -d {home}/compdump",
        f"source {path}",
        "PS1='$ '",
    ]
    _ = (home / ".zshrc").write_text("\n".join(lines) + "\n", encoding="utf-8")
    descriptor, terminal = pty.openpty()
    process = subprocess.Popen(
        [ZSH, "--no-globalrcs", "-i"],
        stdin=terminal,
        stdout=terminal,
        stderr=terminal,
        cwd=cwd,
        env={**os.environ, "ZDOTDIR": str(home)},
        start_new_session=True,
    )
    os.close(terminal)
    try:
        _ = read_until(descriptor, b"$ ")
        _ = os.write(descriptor, typed.encode() + b"\t")
        time.sleep(0.5)
        _ = os.write(descriptor, b"\x01print -r -- '<\x05>'\n")
        output = read_until(descriptor, b">\r\n").decode(errors="replace")
    finally:
        process.kill()
        _ = process.wait()
        os.close(descriptor)
    lines = [line for line in output.replace("\r", "").split("\n") if line[:1] == "<"]
    return lines[-1][1:-1]


def read_until(descriptor: int, marker: bytes) -> bytes:
    output = b""
    deadline = time.monotonic() + 10
    while marker not in output:
        assert time.monotonic() < deadline, f"never saw {marker!r} in {output!r}"
        ready, _, _ = select.select([descriptor], [], [], 0.1)
        if ready:
            output += os.read(descriptor, 4096)
    return output


@POSIX
@pytest.mark.skipif(BASH is None, reason="needs bash")
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("notes ", ["add", "list", "plain", "tags"]),
        ("notes ta", ["tags"]),
        ("notes -", ["--help", "--quiet", "--version", "-h", "-q"]),
        ("notes -q -", ["--help", "--version", "-h"]),
        (
            "notes add -",
            ["--attach", "--color", "--help", "--tag", "--version", "-a", "-h", "-t"],
        ),
        ("notes add --color ", ["dark-red", "red"]),
        ("notes add --color=da", ["dark-red"]),
        ("notes add -t x --", ["--attach", "--color", "--help", "--version"]),
        ("notes add -a a.txt -a ", ["a.txt", "docs"]),
        ("notes add -- -", []),
        ("notes list ", ["docs"]),
        ("notes list --sort ", ["modified", "name", "size"]),
        ("notes list -vs n", ["name"]),
        ("notes list -v -v --verb", ["--verbose"]),
        ("notes tags ", ["rename"]),
        ("notes plain -", ["--version"]),
        ("notes nope ", []),
        ("notes add -5 ", []),
    ],
)
def test_bash_completes_from_the_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    place: Path,
    line: str,
    expected: list[str],
) -> None:
    path = script("bash", monkeypatch, tmp_path)

    assert bash(path, line, place) == sorted(expected)


@POSIX
@pytest.mark.skipif(FISH is None, reason="needs fish")
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "notes ",
            [
                "add\tAdd a note.",
                "list\tList notes.",
                "plain\tShow nothing.",
                "tags\tWork with tags.",
            ],
        ),
        ("notes add --c", ["--color\tDon't pick more than one."]),
        ("notes list --s", ["--sort\tSort by name\\size."]),
        (
            "notes -q -",
            [
                "--help\tShow this help and exit.",
                "--version\tShow the version and exit.",
                "-h\tShow this help and exit.",
            ],
        ),
        ("notes add --color=da", ["--color=dark-red"]),
        ("notes list -vs ", ["modified", "name", "size"]),
        ("notes list d", ["docs/\tDirectory"]),
        ("notes add -a ", ["a.txt", "docs/"]),
        ("notes nope ", []),
        ("notes add -- -", []),
    ],
)
def test_fish_completes_from_the_tree_with_descriptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    place: Path,
    line: str,
    expected: list[str],
) -> None:
    path = script("fish", monkeypatch, tmp_path)

    assert fish(path, line, place) == sorted(expected)


@POSIX
@pytest.mark.skipif(ZSH is None, reason="needs zsh")
@pytest.mark.parametrize(
    ("typed", "completed"),
    [
        ("notes ta", "notes tags"),
        ("notes add --co", "notes add --color"),
        ("notes add --color=dark", "notes add --color=dark-red"),
        ("notes list --sort mod", "notes list --sort modified"),
        ("notes list d", "notes list docs"),
        ("notes -q --ver", "notes -q --version"),
    ],
)
def test_zsh_completes_in_a_real_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    place: Path,
    typed: str,
    completed: str,
) -> None:
    path = script("zsh", monkeypatch, tmp_path)

    assert zsh(path, typed, place) == completed


@POSIX
@pytest.mark.skipif(ZSH is None, reason="needs zsh")
def test_zsh_without_compinit_says_how_to_load_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert ZSH is not None
    path = script("zsh", monkeypatch, tmp_path)

    result = subprocess.run(
        [ZSH, "-f", "-c", 'source "$1"', "zsh", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stderr == (
        "notes: completion needs zsh's completion system. Load it first, "
        "for example in ~/.zshrc: autoload -Uz compinit && compinit\n"
    )


def test_completion_isnt_in_help_or_suggestions() -> None:
    assert "--completion" not in run(notes, ["--help"]).stdout
    assert "--completion" not in run(notes, ["--complet"]).stderr


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--completion"], "--completion needs a shell: bash, zsh, fish."),
        (["--completion", "-q"], "--completion needs a shell: bash, zsh, fish."),
        (
            ["--completion", "fsh"],
            "--completion: 'fsh' isn't one of bash, zsh, fish. Did you mean 'fish'?",
        ),
        (["add", "--completion", "zsh"], "unknown option '--completion'."),
    ],
)
def test_a_wrong_completion_request_is_invalid_input(
    args: list[str], error: str
) -> None:
    result = run(notes, args)

    assert result.returncode == 2
    assert result.stderr.startswith(f"error: {error}\n")


def test_the_script_registers_the_name_the_program_was_run_as(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["/opt/bin/my notes"])
    assert "complete -F _cliron_my_notes 'my notes'" in (
        run(notes, ["--completion=bash"]).stdout
    )
    assert "complete -c 'my notes' -f -a '(_cliron_my_notes)'" in (
        run(notes, ["--completion", "fish"]).stdout
    )
    monkeypatch.setattr(sys, "argv", [""])
    assert "compdef _cliron_notes notes\n" in run(notes, ["--completion", "zsh"]).stdout


def test_your_own_completion_option_wins() -> None:
    @command("ask")
    @option("completion", help="Text to complete.")
    def ask(completion: str = "") -> str:
        return f"completing {completion}"

    assert run(ask, ["--completion", "zsh"]).stdout == "completing zsh\n"


def test_generating_a_script_runs_nothing() -> None:
    calls: list[str] = []

    @group("tool")
    def tool() -> None:
        calls.append("group")

    @command("show")
    @Locked("secret")
    def show(secret: str) -> str:
        calls.append("show")
        return secret

    tool.add(show)

    assert run(tool, ["--completion", "bash"]).returncode == 0
    assert calls == []
