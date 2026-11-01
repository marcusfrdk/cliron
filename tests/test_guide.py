import os
import re
import runpy
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from cliron import command, group
from cliron.testing import validate

ROOT = Path(__file__).parent.parent
DOCUMENTS = ("README.md", "GUIDE.md")
BLOCK = re.compile(r"^```(\w*)\n(.*?)^```$", re.MULTILINE | re.DOTALL)
SCRIPT = re.compile(r"\bpython (\S+\.py)\b")

POSIX = pytest.mark.skipif(
    sys.platform == "win32", reason="runs the examples in a POSIX shell"
)


@command("sample")
def sample_command() -> None: ...


@group("sample")
def sample_group() -> None: ...


@dataclass(frozen=True)
class Example:
    document: str
    line: int
    code: str
    console: str | None

    @property
    def name(self) -> str:
        return f"{self.document}:{self.line}"


def examples() -> list[Example]:
    found: list[Example] = []
    for document in DOCUMENTS:
        text = (ROOT / document).read_text(encoding="utf-8")
        blocks = list(BLOCK.finditer(text))
        for index, block in enumerate(blocks):
            if block.group(1) != "python":
                continue
            following = blocks[index + 1] if index + 1 < len(blocks) else None
            console = (
                following.group(2)
                if following is not None and following.group(1) == "console"
                else None
            )
            line = text.count("\n", 0, block.start()) + 1
            found.append(Example(document, line, block.group(2), console))
    return found


EXAMPLES = examples()


def session(console: str) -> list[tuple[str, str]]:
    steps: list[tuple[str, list[str]]] = []
    for line in console.splitlines():
        if line.startswith("$ "):
            steps.append((line.removeprefix("$ "), []))
        else:
            steps[-1][1].append(line)
    return [(typed, "".join(f"{line}\n" for line in lines)) for typed, lines in steps]


def environment() -> dict[str, str]:
    kept = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CLIRON_", "NOTES_"))
    }
    return kept | {
        "PYTHON": sys.executable,
        "COLUMNS": "80",
        "PYTHONUNBUFFERED": "1",
    }


@pytest.mark.parametrize("example", EXAMPLES, ids=[each.name for each in EXAMPLES])
def test_an_example_defines_valid_clis_and_passing_tests(
    example: Example, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "example.py"
    _ = script.write_text(example.code, encoding="utf-8")

    namespace = cast(
        "dict[str, object]", runpy.run_path(str(script), run_name="example")
    )

    for value in namespace.values():
        if isinstance(value, type(sample_command) | type(sample_group)):
            validate(value)
    for name, value in namespace.items():
        if name.startswith("test_") and callable(value):
            _ = value()


@POSIX
@pytest.mark.parametrize(
    "example",
    [each for each in EXAMPLES if each.console is not None],
    ids=[each.name for each in EXAMPLES if each.console is not None],
)
def test_an_example_prints_what_the_docs_show(example: Example, tmp_path: Path) -> None:
    assert example.console is not None
    steps = session(example.console)
    match = SCRIPT.search(steps[0][0])
    assert match is not None, f"{example.name}: no 'python name.py' to run"
    _ = (tmp_path / match.group(1)).write_text(example.code, encoding="utf-8")

    for typed, expected in steps:
        result = subprocess.run(
            ["/bin/sh", "-c", f'python() {{ "$PYTHON" "$@"; }}; {typed}'],
            cwd=tmp_path,
            env=environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            check=False,
        )

        assert result.stdout == expected, f"{example.name}: $ {typed}"
