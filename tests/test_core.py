import ast
from importlib.metadata import requires, version
from pathlib import Path

import cliron
from cliron import _core


def test_version_comes_from_extension() -> None:
    assert cliron.__version__ == _core.__version__


def test_version_matches_package_metadata() -> None:
    assert cliron.__version__ == version("cliron")


def test_has_no_runtime_dependencies() -> None:
    assert requires("cliron") is None


def parse_stub() -> ast.Module:
    stub_path = Path(_core.__file__).with_name("_core.pyi")
    return ast.parse(stub_path.read_text(encoding="utf-8"))


def test_stub_declares_every_extension_item() -> None:
    declared: set[str] = set()
    for node in parse_stub().body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared.add(node.target.id)
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            declared.add(node.name)
    assert declared == set(_core.__all__)


def test_stub_all_matches_extension_all() -> None:
    stub_all = next(
        node.value
        for node in parse_stub().body
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "__all__"
    )
    assert isinstance(stub_all, ast.List)
    listed = {
        element.value for element in stub_all.elts if isinstance(element, ast.Constant)
    }
    assert listed == set(_core.__all__)
