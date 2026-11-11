import functools
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

import pytest

from cliron import command, group
from cliron.testing import run, validate

REPORT_MODULE = """
from cliron import command


@command("report", platforms="linux")
def report() -> str:
    return "sales: 42"


@command("open_report", platforms=["macos", "linux"])
def open_report() -> str:
    return "sales: 42"
"""


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def never() -> bool:
    return False


def broken() -> bool:
    message = "the roles file is missing"
    raise RuntimeError(message)


@group("tool")
def tool() -> None:
    """Run the tool."""


@command("status")
def status() -> str:
    """Show the status."""
    return "fine"


@command("mount", platforms="linux")
def mount() -> str:
    """Mount a drive."""
    return "mounted"


@command("watch", platforms=["macos", "linux"])
def watch() -> str:
    """Watch for changes."""
    return "watching"


@group("registry", platforms="windows")
def registry() -> None:
    """Edit the registry."""


@command("read_key")
def read_key() -> str:
    """Read a key."""
    return "key"


registry.add(read_key)
tool.add(status, mount, watch, registry)


@pytest.mark.parametrize(
    ("system", "args", "output"),
    [
        ("linux", ["mount"], "mounted\n"),
        ("linux", ["watch"], "watching\n"),
        ("darwin", ["watch"], "watching\n"),
        ("win32", ["registry", "read-key"], "key\n"),
    ],
)
def test_a_command_runs_on_its_platforms(
    monkeypatch: pytest.MonkeyPatch, system: str, args: list[str], output: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)

    result = run(tool, args)

    assert result.stdout == output
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("system", "args", "message"),
    [
        ("darwin", ["mount"], "'tool mount' runs only on Linux."),
        ("win32", ["mount", "--help"], "'tool mount' runs only on Linux."),
        ("win32", ["watch"], "'tool watch' runs only on Linux and macOS."),
        ("freebsd14", ["watch"], "'tool watch' runs only on Linux and macOS."),
        (
            "linux",
            ["registry", "read-key"],
            "'tool registry' runs only on Windows.",
        ),
    ],
)
def test_a_command_on_another_platform_says_where_it_runs(
    monkeypatch: pytest.MonkeyPatch, system: str, args: list[str], message: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)

    result = run(tool, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == f"error: {message}\nRun 'tool --help' for usage.\n"


@pytest.mark.parametrize(
    ("system", "commands"),
    [
        (
            "linux",
            (
                "  status      Show the status.\n"
                "  mount       Mount a drive.\n"
                "  watch       Watch for changes.\n"
            ),
        ),
        (
            "darwin",
            "  status      Show the status.\n  watch       Watch for changes.\n",
        ),
        (
            "win32",
            "  status      Show the status.\n  registry    Edit the registry.\n",
        ),
    ],
)
def test_help_lists_only_the_commands_for_this_platform(
    monkeypatch: pytest.MonkeyPatch, system: str, commands: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)

    assert run(tool, ["--help"]).stdout.endswith(f"Commands:\n{commands}")


@pytest.mark.parametrize(
    ("system", "error"),
    [
        ("darwin", "error: 'moun' isn't a tool command.\n"),
        ("linux", "error: 'moun' isn't a tool command. Did you mean 'mount'?\n"),
    ],
)
def test_suggestions_offer_only_the_commands_for_this_platform(
    monkeypatch: pytest.MonkeyPatch, system: str, error: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)

    assert run(tool, ["moun"]).stderr.startswith(error)


@pytest.mark.parametrize(
    ("system", "offered", "left_out"),
    [
        ("linux", ["mount", "watch"], ["registry", "read-key"]),
        ("darwin", ["watch"], ["mount", "registry", "read-key"]),
        ("win32", ["registry", "read-key"], ["mount", "watch"]),
    ],
)
def test_completion_offers_only_the_commands_for_this_platform(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    offered: list[str],
    left_out: list[str],
) -> None:
    monkeypatch.setattr(sys, "platform", system)

    script = run(tool, ["--completion", "bash"]).stdout

    assert all(name in script for name in offered)
    assert not any(name in script for name in left_out)


def test_a_top_command_on_another_platform_says_where_it_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    @command("solo", platforms=["windows", "linux"])
    def solo() -> str:
        return "ran"

    for args in [[], ["--help"]]:
        result = run(solo, args)

        assert result.returncode == 2
        assert result.stderr == "error: 'solo' runs only on Linux and Windows.\n"


def test_every_platform_is_named_when_none_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd14")

    @command("solo", platforms=["windows", "macos", "linux"])
    def solo() -> str:
        return "ran"

    assert run(solo, []).stderr == (
        "error: 'solo' runs only on Linux, macOS and Windows.\n"
    )


def test_enabled_is_called_only_on_the_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @group("tool")
    def tool() -> None: ...

    @command("mount", platforms="linux", enabled=broken)
    def mount() -> None: ...

    tool.add(mount)
    monkeypatch.setattr(sys, "platform", "darwin")

    assert run(tool, ["mount"]).stderr.startswith(
        "error: 'tool mount' runs only on Linux.\n"
    )

    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(RuntimeError, match="the roles file is missing"):
        _ = run(tool, ["mount"])


def test_a_command_disabled_on_its_platform_says_it_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    @group("tool")
    def tool() -> None: ...

    @command("mount", platforms="linux", enabled=never)
    def mount() -> None: ...

    tool.add(mount)

    assert run(tool, ["mount"]).stderr.startswith("error: 'tool mount' is disabled.\n")


@pytest.mark.parametrize(
    ("platforms", "error", "message"),
    [
        (
            3,
            TypeError,
            (
                "{caller} takes platforms as a string or a list of strings, such as "
                "'linux' or ['linux', 'macos'], not 3."
            ),
        ),
        (
            ["linux", 3],
            TypeError,
            (
                "{caller} takes platforms as a string or a list of strings, such as "
                "'linux' or ['linux', 'macos'], not ['linux', 3]."
            ),
        ),
        (
            "macOS",
            ValueError,
            "'macOS' isn't a platform. Use 'linux', 'macos' or 'windows'.",
        ),
        (
            ["linux", "darwin"],
            ValueError,
            "'darwin' isn't a platform. Use 'linux', 'macos' or 'windows'.",
        ),
        (
            ["linux", "linux"],
            ValueError,
            "platforms of {caller} lists 'linux' twice. Remove one.",
        ),
        (
            [],
            ValueError,
            (
                "platforms of {caller} is empty. Name at least one, or leave "
                "platforms out to run on every platform."
            ),
        ),
    ],
)
@pytest.mark.parametrize("caller", ["@command", "@group", "lazy()"])
def test_platforms_must_name_each_known_platform_once(
    platforms: object, error: type[Exception], message: str, caller: str
) -> None:
    @group("tool")
    def tool() -> None: ...

    makers: dict[str, Callable[..., object]] = {
        "@command": command,
        "@group": group,
        "lazy()": functools.partial(tool.lazy, target="platforms_report:report"),
    }

    with pytest.raises(error, match=exactly(message.format(caller=caller))):
        _ = makers[caller]("report", platforms=platforms)


@pytest.fixture
def modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    _ = (tmp_path / "platforms_report.py").write_text(REPORT_MODULE, encoding="utf-8")
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        del sys.modules[name]


@pytest.mark.usefixtures("modules")
def test_a_lazy_command_on_another_platform_is_never_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    @group("shop")
    def shop() -> None: ...

    shop.lazy("report", "platforms_report:report", platforms="linux")

    assert run(shop, ["--help"]).stdout.endswith(
        "  -h, --help  Show this help and exit.\n"
    )
    assert run(shop, ["report"]).stderr.startswith(
        "error: 'shop report' runs only on Linux.\n"
    )
    assert "platforms_report" not in sys.modules

    monkeypatch.setattr(sys, "platform", "linux")

    assert run(shop, ["report"]).stdout == "sales: 42\n"


@pytest.mark.usefixtures("modules")
def test_a_lazy_command_may_list_its_platforms_in_any_order() -> None:
    @group("shop")
    def shop() -> None: ...

    shop.lazy(
        "open_report", "platforms_report:open_report", platforms=["linux", "macos"]
    )

    validate(shop)


@pytest.mark.parametrize(
    ("attribute", "platforms", "message"),
    [
        (
            "report",
            None,
            (
                "lazy command 'report' has platforms=None, but the command it loads "
                "has platforms=['linux']. Give both the same platforms."
            ),
        ),
        (
            "open_report",
            "macos",
            (
                "lazy command 'open-report' has platforms=['macos'], but the command "
                "it loads has platforms=['linux', 'macos']. Give both the same "
                "platforms."
            ),
        ),
    ],
)
@pytest.mark.usefixtures("modules")
def test_a_lazy_command_and_what_it_loads_must_agree(
    attribute: str, platforms: Literal["macos"] | None, message: str
) -> None:
    @group("shop")
    def shop() -> None: ...

    shop.lazy(attribute, f"platforms_report:{attribute}", platforms=platforms)

    with pytest.raises(ValueError, match=exactly(message)):
        validate(shop)
