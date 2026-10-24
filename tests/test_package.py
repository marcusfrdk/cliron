import importlib
import subprocess
import sys
from importlib.metadata import requires, version

import pytest

import cliron
import cliron.testing


def test_version_matches_package_metadata() -> None:
    assert cliron.__version__ == version("cliron")


def test_has_no_runtime_dependencies() -> None:
    assert requires("cliron") is None


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        _ = cliron.missing


@pytest.mark.parametrize("name", cliron.__all__)
def test_every_public_name_resolves(name: str) -> None:
    assert getattr(cliron, name) is not None


@pytest.mark.parametrize("name", cliron.testing.__all__)
def test_every_testing_name_resolves(name: str) -> None:
    assert getattr(cliron.testing, name) is not None


def test_dir_lists_every_public_name() -> None:
    assert set(cliron.__all__) <= set(dir(cliron))


def test_import_loads_no_private_module(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in sys.modules if name.split(".")[0] == "cliron"]:
        monkeypatch.delitem(sys.modules, name)

    _ = importlib.import_module("cliron")

    assert [name for name in sys.modules if name.startswith("cliron.")] == []


STDLIB_PROBE = """
import sys

from cliron import argument, command, group

@group("notes")
def notes() -> None: ...

@command("add")
@argument("text")
def add(text: str) -> None: ...

notes.add(add)

sys.argv = ["notes", "add", "milk"]
try:
    notes()
except SystemExit:
    pass
print(sorted(name for name in ("difflib", "json", "subprocess") if name in sys.modules))
"""


def test_a_run_loads_json_difflib_and_subprocess_only_when_needed() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-c", STDLIB_PROBE],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "[]\n"
