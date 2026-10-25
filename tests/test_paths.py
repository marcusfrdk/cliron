import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Literal

import pytest

from cliron import (
    Child,
    argument,
    command,
    directory,
    env,
    file,
    flag,
    option,
    stdin,
)
from cliron.testing import run, validate

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def _case_id(case: object) -> str:
    return case if isinstance(case, str) else repr(case)


@pytest.fixture
def places(tmp_path: Path) -> dict[str, Path]:
    found = tmp_path / "notes.txt"
    _ = found.write_text("Buy milk", encoding="utf-8")
    (tmp_path / "photos").mkdir()
    return {
        "file": found,
        "directory": tmp_path / "photos",
        "missing": tmp_path / "missing",
    }


class Positive(Child[int, int]):
    default_check: ClassVar[Literal["definition", "run"]] = "run"

    def process(self, value: int, /) -> int:
        if value < 1:
            message = f"{value} isn't positive."
            raise ValueError(message)
        return value


@pytest.mark.parametrize(
    ("check", "place", "problem"),
    [
        (file(), "file", None),
        (file(), "missing", "doesn't exist."),
        (file(), "directory", "is a directory, not a file."),
        (file(exists=False), "missing", None),
        (file(exists=False), "file", "already exists."),
        (file(exists=False), "directory", "already exists."),
        (file(exists=None), "file", None),
        (file(exists=None), "missing", None),
        (file(exists=None), "directory", "is a directory, not a file."),
        (directory(), "directory", None),
        (directory(), "missing", "doesn't exist."),
        (directory(), "file", "isn't a directory."),
        (directory(exists=False), "missing", None),
        (directory(exists=False), "directory", "already exists."),
        (directory(exists=False), "file", "already exists."),
        (directory(exists=None), "directory", None),
        (directory(exists=None), "missing", None),
        (directory(exists=None), "file", "isn't a directory."),
    ],
    ids=_case_id,
)
def test_a_path_check_accepts_or_rejects_each_kind_of_place(
    places: dict[str, Path],
    check: Child[Path, Path],
    place: str,
    problem: str | None,
) -> None:
    path = places[place]

    result = _show(check, [str(path)])

    if problem is None:
        assert (result.returncode, result.stdout) == (0, f"{path.name}\n")
    else:
        assert result.returncode == 2
        assert result.stderr == (
            f"error: PATH: '{path}' {problem}\nRun 'show --help' for usage.\n"
        )


@pytest.mark.parametrize(
    ("check", "sentence"),
    [
        (file(), "Must be an existing file."),
        (file(exists=False), "Must not exist yet."),
        (file(exists=None), "Must not be a directory."),
        (directory(), "Must be an existing directory."),
        (directory(exists=False), "Must not exist yet."),
        (directory(exists=None), "Must be a directory if it exists."),
    ],
)
def test_help_says_what_a_path_check_accepts(
    check: Child[Path, Path], sentence: str
) -> None:
    lines = _show(check, ["--help"]).stdout.splitlines()

    assert lines[lines.index("Arguments:") + 1].split(maxsplit=1) == ["PATH", sentence]


def test_each_path_of_a_list_is_checked(places: dict[str, Path]) -> None:
    @command("show")
    @argument("paths")
    @file()
    def show(paths: list[Path]) -> int:
        return len(paths)

    found, missing, folder = places["file"], places["missing"], places["directory"]

    assert run(show, [str(found), str(missing), str(folder)]).stderr == (
        f"error: PATHS: '{missing}' doesn't exist.\n"
        f"error: PATHS: '{folder}' is a directory, not a file.\n"
        "Run 'show --help' for usage.\n"
    )


def test_each_piped_line_is_checked(places: dict[str, Path]) -> None:
    @command("show")
    @stdin("paths")
    @file()
    def show(paths: list[Path]) -> int:
        return len(paths)

    missing = places["missing"]

    assert run(show, [], input=f"{places['file']}\n{missing}").stderr == (
        f"error: stdin: line 2: '{missing}' doesn't exist.\n"
        "Run 'show --help' for usage.\n"
    )


def test_a_path_from_an_environment_variable_is_checked(
    places: dict[str, Path],
) -> None:
    @command("show")
    @env("config")
    @file()
    def show(config: Path) -> str:
        return config.name

    missing = places["missing"]

    assert run(show, [], env={"CONFIG": str(missing)}).stderr == (
        f"error: $CONFIG: '{missing}' doesn't exist.\nRun 'show --help' for usage.\n"
    )


def test_a_default_path_is_checked_on_each_run_that_uses_it(
    places: dict[str, Path],
) -> None:
    missing = places["missing"]

    def show(config: Path = missing) -> str:
        return config.name

    cli = command("show")(option("config")(file()(show)))

    validate(cli)
    assert run(cli, []).stderr == (
        f"error: --config: '{missing}' doesn't exist.\nRun 'show --help' for usage.\n"
    )
    assert run(cli, ["--config", str(places["file"])]).stdout == "notes.txt\n"


def test_each_path_of_a_default_is_checked(places: dict[str, Path]) -> None:
    found, missing = places["file"], places["missing"]

    def show(paths: tuple[Path, ...] = (found, missing)) -> int:
        return len(paths)

    cli = command("show")(option("paths")(file()(show)))

    assert run(cli, []).stderr == (
        f"error: --paths: '{missing}' doesn't exist.\nRun 'show --help' for usage.\n"
    )


def test_a_default_that_passes_or_is_none_reaches_the_function(
    places: dict[str, Path],
) -> None:
    found = places["file"]

    def show(config: Path = found, extra: Path | None = None) -> str:
        return f"{config.name} {extra}"

    cli = command("show")(option("config")(file()(option("extra")(file()(show)))))

    assert run(cli, []).stdout == "notes.txt None\n"


def test_a_child_can_check_the_default_on_each_run() -> None:
    @command("pick")
    @option("count")
    @Positive()
    @flag("verbose", "-v")
    @Positive()
    def pick(count: int = 0, verbose: int = 0) -> str:
        return f"{count} {verbose}"

    validate(pick)
    assert run(pick, []).stderr == (
        "error: --count: 0 isn't positive.\n"
        "error: --verbose: 0 isn't positive.\n"
        "Run 'pick --help' for usage.\n"
    )
    assert run(pick, ["--count", "2", "-vv"]).stdout == "2 2\n"


@pytest.mark.parametrize(
    ("check", "annotation", "message"),
    [
        (file(), str, "@file() takes Path, but parameter 'path' has the type str."),
        (
            file(exists=None),
            int,
            "@file(exists=None) takes Path, but parameter 'path' has the type int.",
        ),
        (
            directory(exists=False),
            str,
            (
                "@directory(exists=False) takes Path, but parameter 'path' "
                "has the type str."
            ),
        ),
    ],
)
def test_a_path_check_only_fits_a_path(
    check: Child[Path, Path], annotation: object, message: str
) -> None:
    def show(path: object) -> str:
        return f"{path}"

    show.__annotations__["path"] = annotation

    with pytest.raises(TypeError, match=exactly(message)):
        validate(command("show")(argument("path")(check(show))))


@pytest.mark.parametrize(
    ("make", "exists", "message"),
    [
        (file, "yes", "@file takes exists=True, False or None, not 'yes'."),
        (directory, 1, "@directory takes exists=True, False or None, not 1."),
    ],
)
def test_exists_must_be_true_false_or_none(
    make: Callable[..., object], exists: object, message: str
) -> None:
    with pytest.raises(TypeError, match=exactly(message)):
        _ = make(exists=exists)


@POSIX
def test_anything_but_a_directory_counts_as_a_file() -> None:
    assert _show(file(), [os.devnull]).stdout == "null\n"


@POSIX
def test_a_broken_symbolic_link_counts_as_missing(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "gone")

    assert _show(file(), [str(link)]).stderr == (
        f"error: PATH: '{link}' doesn't exist.\nRun 'show --help' for usage.\n"
    )


def _show(
    check: Child[Path, Path], args: list[str]
) -> subprocess.CompletedProcess[str]:
    def show(path: Path) -> str:
        return path.name

    return run(command("show")(argument("path")(check(show))), args)
