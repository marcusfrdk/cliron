import importlib
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest

from cliron import command, group
from cliron.testing import run, validate

REPORT = '''
from cliron import command, option


def quarters(typed: str) -> list[str]:
    return [quarter for quarter in ("q1", "q2", "q3") if quarter.startswith(typed)]


@command("report", aliases="rep")
@option("quarter", completions=quarters)
def report(quarter: str = "q1") -> str:
    """Summarize sales, slowly."""
    return f"sales in {quarter}: 42"


TEXT = "not a command"
'''

ADMIN = '''
from cliron import command, group


@group("admin")
def admin() -> None:
    """Manage the shop."""


@command("users")
def users() -> str:
    """List users."""
    return "ada, grace"


admin.add(users)
'''

BROKEN = """
import lazy_not_installed
"""

Run = Callable[[list[str]], subprocess.CompletedProcess[str]]


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


@pytest.fixture
def modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    for name, text in [
        ("lazy_report", REPORT),
        ("lazy_admin", ADMIN),
        ("lazy_broken", BROKEN),
    ]:
        _ = (tmp_path / f"{name}.py").write_text(text, encoding="utf-8")
    before = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - before:
        del sys.modules[name]


@pytest.fixture
def shop(modules: Path) -> Run:
    _ = modules

    @group("shop")
    def tool() -> None:
        """Run the shop."""

    @command("hello")
    def hello() -> str:
        """Say hello."""
        return "hello"

    tool.add(hello)
    tool.lazy("report", "lazy_report:report", aliases="rep", help="Summarize sales.")
    tool.lazy("admin", "lazy_admin:admin", help="Manage the shop.")

    def run_shop(args: list[str]) -> subprocess.CompletedProcess[str]:
        return run(tool, args)

    return run_shop


def test_help_lists_a_lazy_command_without_importing_it(shop: Run) -> None:
    commands = (
        "Commands:\n"
        "  hello        Say hello.\n"
        "  report, rep  Summarize sales.\n"
        "  admin        Manage the shop.\n"
    )

    assert shop(["--help"]).stdout.endswith(commands)
    assert "lazy_report" not in sys.modules


@pytest.mark.parametrize(
    "args", [["hello"], ["repot"], ["--completion", "values", "", "nope", ""]]
)
def test_other_commands_and_mistakes_dont_import_it(shop: Run, args: list[str]) -> None:
    _ = shop(args)

    assert "lazy_report" not in sys.modules


@pytest.mark.parametrize(
    ("args", "output"),
    [
        (["report"], "sales in q1: 42\n"),
        (["rep", "--quarter", "q2"], "sales in q2: 42\n"),
        (["admin", "users"], "ada, grace\n"),
        (["--completion", "values", "report", "quarter", "q"], "q1\nq2\nq3\n"),
    ],
)
def test_running_it_imports_it(shop: Run, args: list[str], output: str) -> None:
    result = shop(args)

    assert result.stdout == output
    assert result.returncode == 0


def test_its_own_help_comes_from_its_module(shop: Run) -> None:
    assert shop(["report", "--help"]).stdout.startswith(
        "Usage: shop report [OPTIONS]\n\nSummarize sales, slowly.\n"
    )


def test_it_is_imported_once(shop: Run) -> None:
    assert shop(["report"]).stdout == shop(["rep"]).stdout


def test_the_completion_script_includes_it(shop: Run) -> None:
    script = shop(["--completion", "bash"]).stdout

    assert "--quarter" in script
    assert "users" in script


@pytest.mark.usefixtures("modules")
def test_validate_imports_everything() -> None:

    @group("shop")
    def shop() -> None: ...

    shop.lazy("report", "lazy_report:report", aliases="rep")
    shop.lazy("admin", "lazy_admin:admin")

    validate(shop)

    assert {"lazy_report", "lazy_admin"} <= set(sys.modules)


@pytest.mark.usefixtures("modules")
def test_without_help_its_row_has_no_text() -> None:

    @group("shop")
    def shop() -> None: ...

    shop.lazy("admin", "lazy_admin:admin")

    assert run(shop, ["--help"]).stdout.endswith("Commands:\n  admin\n")


@pytest.mark.usefixtures("modules")
@pytest.mark.parametrize(
    ("name", "target", "aliases", "error", "message"),
    [
        (
            "report",
            "lazy_nowhere:report",
            (),
            ImportError,
            (
                "lazy command 'report' can't load 'lazy_nowhere:report': "
                "No module named 'lazy_nowhere'."
            ),
        ),
        (
            "report",
            "lazy_report:nope",
            (),
            ImportError,
            (
                "lazy command 'report' can't load 'lazy_report:nope': "
                "module 'lazy_report' has no attribute 'nope'."
            ),
        ),
        (
            "report",
            "lazy_report:TEXT",
            (),
            TypeError,
            (
                "lazy command 'report' loaded 'not a command' from 'lazy_report:TEXT', "
                "which isn't a command or group. Point it at a function decorated "
                "with @command or @group."
            ),
        ),
        (
            "summary",
            "lazy_report:report",
            (),
            ValueError,
            (
                "lazy command 'summary' loaded command 'report' from "
                "'lazy_report:report'. Give both the same name."
            ),
        ),
        (
            "report",
            "lazy_report:report",
            ("rp",),
            ValueError,
            (
                "lazy command 'report' has the aliases ['rp'], but the command it "
                "loads has ['rep']. Give both the same aliases."
            ),
        ),
        (
            "admin",
            "lazy_admin:admin",
            ("adm",),
            ValueError,
            (
                "lazy command 'admin' has the aliases ['adm'], but the group it loads "
                "has []. Give both the same aliases."
            ),
        ),
    ],
)
def test_a_lazy_command_that_doesnt_fit_is_a_mistake(
    name: str,
    target: str,
    aliases: tuple[str, ...],
    error: type[Exception],
    message: str,
) -> None:
    @group("shop")
    def shop() -> None: ...

    shop.lazy(name, target, aliases=aliases)

    with pytest.raises(error, match=exactly(message)):
        _ = run(shop, [name])
    with pytest.raises(error, match=exactly(message)):
        validate(shop)


def test_a_mistake_found_by_a_run_exits_with_1(modules: Path) -> None:
    source = (
        "from cliron import group\n"
        "\n"
        "@group('shop')\n"
        "def shop() -> None: ...\n"
        "\n"
        "shop.lazy('report', 'lazy_nowhere:report')\n"
        "shop()\n"
    )
    _ = (modules / "lazy_shop.py").write_text(source, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "lazy_shop", "report"],
        cwd=modules,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr == (
        "error: lazy command 'report' can't load 'lazy_nowhere:report': "
        "No module named 'lazy_nowhere'.\n"
    )


@pytest.mark.usefixtures("modules")
def test_an_error_inside_its_module_is_raised_as_it_is() -> None:
    @group("shop")
    def shop() -> None: ...

    shop.lazy("broken", "lazy_broken:broken")

    with pytest.raises(ModuleNotFoundError, match="lazy_not_installed"):
        _ = run(shop, ["broken"])


def test_a_lazy_group_cant_be_the_group_itself(modules: Path) -> None:
    source = (
        "from cliron import group\n"
        "\n"
        "@group('shop')\n"
        "def shop() -> None: ...\n"
        "\n"
        "shop.lazy('shop', 'lazy_shop:shop')\n"
    )
    _ = (modules / "lazy_shop.py").write_text(source, encoding="utf-8")

    @group("sample")
    def sample() -> None: ...

    shop = cast("object", vars(importlib.import_module("lazy_shop"))["shop"])
    assert isinstance(shop, type(sample))

    message = "group 'shop' can't be added to itself."
    with pytest.raises(ValueError, match=exactly(message)):
        validate(shop)


@pytest.mark.parametrize(
    ("args", "options", "error", "message"),
    [
        (
            [3, "lazy_report:report"],
            {},
            TypeError,
            "lazy() takes the name as a string, such as 'archive', not 3.",
        ),
        (
            ["Report", "lazy_report:report"],
            {},
            ValueError,
            "'Report' isn't snake_case. Use 'report'.",
        ),
        (
            ["report", 3],
            {},
            TypeError,
            (
                "lazy() takes the target as a string, such as 'notes.archive:archive', "
                "not 3."
            ),
        ),
        *(
            (
                ["report", target],
                {},
                ValueError,
                (
                    "lazy() takes the target as 'module:attribute', such as "
                    f"'notes.archive:archive', not {target!r}."
                ),
            )
            for target in ["lazy_report", ":report", "lazy_report:", "lazy.:report"]
        ),
        (
            ["report", "lazy_report:report"],
            {"aliases": 3},
            TypeError,
            (
                "lazy() takes aliases as a name or a list of names, "
                "such as 'ls' or ['ls', 'l'], not 3."
            ),
        ),
        (
            ["report", "lazy_report:report"],
            {"aliases": "report"},
            ValueError,
            "'report' is already the command's name. Remove it from aliases.",
        ),
        (
            ["report", "lazy_report:report"],
            {"help": 3},
            TypeError,
            'lazy() takes help as a string, such as help="How many.", not 3.',
        ),
        (
            ["hello", "lazy_report:report"],
            {},
            ValueError,
            "group 'shop' already has a command 'hello'. Rename one of them.",
        ),
    ],
)
def test_lazy_checks_what_it_is_given(
    args: list[object], options: dict[str, object], error: type[Exception], message: str
) -> None:
    @group("shop")
    def shop() -> None: ...

    @command("hello")
    def hello() -> None: ...

    shop.add(hello)
    lazy = cast("Callable[..., object]", shop.lazy)

    with pytest.raises(error, match=exactly(message)):
        _ = lazy(*args, **options)
