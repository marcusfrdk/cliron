from importlib.metadata import requires, version

import pytest

import cliron


def test_version_matches_package_metadata() -> None:
    assert cliron.__version__ == version("cliron")


def test_has_no_runtime_dependencies() -> None:
    assert requires("cliron") is None


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        _ = cliron.missing
