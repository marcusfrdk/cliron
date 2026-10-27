import functools
import importlib
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest

from cliron import command, group, option
from cliron.testing import run, validate

ROLES: set[str] = set()

ROLE_MODULE = """
ROLES = set()


def is_analyst():
    return "analyst" in ROLES
"""

REPORT_MODULE = """
from cliron import command

from enabled_roles import is_analyst


@command("report", enabled=is_analyst)
def report() -> str:
    return "sales: 42"


@command("open_report")
def open_report() -> str:
    return "sales: 42"
"""


def exactly(message: str) -> str:
    return rf"\A{re.escape(message)}(?:\n|\Z)"


def is_admin() -> bool:
    return "admin" in ROLES


def has_role(role: str) -> bool:
    return role in ROLES


def yes() -> object:
    return "yes"


def broken() -> bool:
    message = "the roles file is missing"
    raise RuntimeError(message)


async def checked_remotely() -> bool:
    return True


def ages(typed: str) -> list[str]:
    return [age for age in ("1d", "7d", "30d") if age.startswith(typed)]


@group("tool")
def tool() -> None:
    """Run the tool."""


@command("status")
def status() -> str:
    """Show the status."""
    return "fine"


@command("purge", aliases="rm", enabled=is_admin)
@option("older_than", completions=ages)
def purge(older_than: str = "30d") -> str:
    """Delete old records."""
    return f"purged {older_than}"


@group("admin", enabled=is_admin)
def admin() -> None:
    """Manage users."""


@command("users")
def users() -> str:
    """List users."""
    return "ada"


admin.add(users)
tool.add(status, purge, admin)


@pytest.fixture(autouse=True)
def no_roles() -> Iterator[None]:
    ROLES.clear()
    yield
    ROLES.clear()


@pytest.fixture
def admin_role() -> None:
    ROLES.add("admin")


@pytest.mark.usefixtures("admin_role")
@pytest.mark.parametrize(
    ("args", "output"),
    [
        (["purge"], "purged 30d\n"),
        (["rm", "--older-than", "7d"], "purged 7d\n"),
        (["admin", "users"], "ada\n"),
    ],
)
def test_an_enabled_command_runs(args: list[str], output: str) -> None:
    result = run(tool, args)

    assert result.stdout == output
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("args", "path"),
    [
        (["purge"], "tool purge"),
        (["rm", "--older-than", "7d"], "tool purge"),
        (["purge", "--help"], "tool purge"),
        (["admin", "users"], "tool admin"),
        (["admin", "nope"], "tool admin"),
    ],
)
def test_a_disabled_command_says_so_and_stops(args: list[str], path: str) -> None:
    result = run(tool, args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: '{path}' is disabled.\nRun 'tool --help' for usage.\n"
    )


def test_help_leaves_out_disabled_commands() -> None:
    assert run(tool, ["--help"]).stdout.endswith(
        "Commands:\n  status      Show the status.\n"
    )


@pytest.mark.usefixtures("admin_role")
def test_help_lists_enabled_commands() -> None:
    commands = (
        "Commands:\n"
        "  status      Show the status.\n"
        "  purge, rm   Delete old records.\n"
        "  admin       Manage users.\n"
    )

    assert run(tool, ["--help"]).stdout.endswith(commands)


def test_suggestions_leave_out_disabled_commands() -> None:
    assert run(tool, ["purg"]).stderr == (
        "error: 'purg' isn't a tool command.\nRun 'tool --help' for usage.\n"
    )


@pytest.mark.usefixtures("admin_role")
def test_suggestions_include_enabled_commands() -> None:
    assert run(tool, ["purg"]).stderr.startswith(
        "error: 'purg' isn't a tool command. Did you mean 'purge'?\n"
    )


def test_completion_leaves_out_disabled_commands() -> None:
    script = run(tool, ["--completion", "bash"]).stdout

    assert "status" in script
    assert "purge" not in script
    assert "users" not in script


@pytest.mark.usefixtures("admin_role")
def test_completion_offers_enabled_commands() -> None:
    script = run(tool, ["--completion", "bash"]).stdout

    assert "purge" in script
    assert "users" in script


@pytest.mark.parametrize(("admin", "output"), [(False, ""), (True, "1d\n")])
def test_completion_values_stop_at_a_disabled_command(
    *, admin: bool, output: str
) -> None:
    if admin:
        ROLES.add("admin")

    result = run(tool, ["--completion", "values", "purge", "older_than", "1"])

    assert result.stdout == output


def test_a_disabled_top_command_says_so() -> None:
    @command("solo", enabled=is_admin)
    def solo() -> str:
        return "ran"

    for args in [[], ["--help"]]:
        result = run(solo, args)

        assert result.returncode == 2
        assert result.stderr == "error: 'solo' is disabled.\n"


def test_any_callable_without_arguments_works() -> None:
    @group("tool")
    def tool() -> None: ...

    @command("partial", enabled=functools.partial(has_role, "admin"))
    def partial() -> str:
        return "partial"

    @command("lambda", enabled=lambda: has_role("admin"))
    def lambda_() -> str:
        return "lambda"

    tool.add(partial, lambda_)

    assert run(tool, ["partial"]).returncode == 2
    ROLES.add("admin")
    assert run(tool, ["partial"]).stdout == "partial\n"
    assert run(tool, ["lambda"]).stdout == "lambda\n"


def test_validate_checks_disabled_commands_without_calling_the_function() -> None:
    @group("tool")
    def tool() -> None: ...

    @command("purge", enabled=broken)
    def purge(older_than: object) -> None:
        _ = older_than

    tool.add(purge)

    message = "parameter 'older_than' has no parent."
    with pytest.raises(TypeError, match=re.escape(message)):
        validate(tool)


def test_an_error_in_the_function_is_raised_as_it_is() -> None:
    @group("tool")
    def tool() -> None: ...

    @command("purge", enabled=broken)
    def purge() -> None: ...

    tool.add(purge)

    with pytest.raises(RuntimeError, match="the roles file is missing"):
        _ = run(tool, ["--help"])


def test_the_function_must_return_a_bool() -> None:
    @group("tool")
    def tool() -> None: ...

    @command("purge", enabled=cast("Callable[[], bool]", yes))
    def purge() -> None: ...

    tool.add(purge)

    message = "enabled function 'yes' returned 'yes'. Make it return True or False."
    with pytest.raises(TypeError, match=exactly(message)):
        _ = run(tool, ["purge"])


@pytest.mark.parametrize(
    ("enabled", "message"),
    [
        (
            True,
            "takes enabled as a function, such as def is_admin() -> bool, not True.",
        ),
        (
            has_role,
            (
                "enabled function 'has_role' must take no arguments. "
                'Wrap it, such as lambda: has_role("admin").'
            ),
        ),
        (
            checked_remotely,
            (
                "enabled function 'checked_remotely' is async def, but help and "
                "completion can't wait for it. Make it a plain function."
            ),
        ),
    ],
)
@pytest.mark.parametrize("caller", ["@command", "@group", "lazy()"])
def test_enabled_must_be_a_plain_function_without_arguments(
    enabled: object, message: str, caller: str
) -> None:
    @group("tool")
    def tool() -> None: ...

    makers: dict[str, Callable[..., object]] = {
        "@command": command,
        "@group": group,
        "lazy()": functools.partial(tool.lazy, target="enabled_report:report"),
    }
    expected = f"{caller} {message}" if message.startswith("takes") else message

    with pytest.raises(TypeError, match=exactly(expected)):
        _ = makers[caller]("report", enabled=enabled)


@pytest.fixture
def modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[set[str]]:
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    _ = (tmp_path / "enabled_roles.py").write_text(ROLE_MODULE, encoding="utf-8")
    _ = (tmp_path / "enabled_report.py").write_text(REPORT_MODULE, encoding="utf-8")
    before = set(sys.modules)
    roles = cast("set[str]", vars(importlib.import_module("enabled_roles"))["ROLES"])
    yield roles
    for name in set(sys.modules) - before:
        del sys.modules[name]


def test_a_disabled_lazy_command_is_never_imported(modules: set[str]) -> None:
    is_analyst = cast(
        "Callable[[], bool]",
        vars(importlib.import_module("enabled_roles"))["is_analyst"],
    )

    @group("shop")
    def shop() -> None: ...

    shop.lazy("report", "enabled_report:report", enabled=is_analyst)

    assert run(shop, ["--help"]).stdout.endswith(
        "  -h, --help  Show this help and exit.\n"
    )
    assert run(shop, ["report"]).stderr.startswith(
        "error: 'shop report' is disabled.\n"
    )
    assert "enabled_report" not in sys.modules

    modules.add("analyst")

    assert run(shop, ["report"]).stdout == "sales: 42\n"


@pytest.mark.parametrize(
    ("attribute", "enabled", "message"),
    [
        (
            "report",
            None,
            (
                "lazy command 'report' has enabled=None, but the command it loads "
                "has enabled=is_analyst. Give both the same function."
            ),
        ),
        (
            "open_report",
            is_admin,
            (
                "lazy command 'open-report' has enabled=is_admin, but the command it "
                "loads has enabled=None. Give both the same function."
            ),
        ),
    ],
)
@pytest.mark.usefixtures("modules")
def test_a_lazy_command_and_what_it_loads_must_agree(
    attribute: str, enabled: Callable[[], bool] | None, message: str
) -> None:
    ROLES.add("admin")

    @group("shop")
    def shop() -> None: ...

    shop.lazy(attribute, f"enabled_report:{attribute}", enabled=enabled)

    with pytest.raises(ValueError, match=exactly(message)):
        validate(shop)
