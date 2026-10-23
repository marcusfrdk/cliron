from importlib.metadata import version

import cliron
from cliron import _core


def test_version_comes_from_extension() -> None:
    assert cliron.__version__ == _core.__version__


def test_version_matches_package_metadata() -> None:
    assert cliron.__version__ == version("cliron")
