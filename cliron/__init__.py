"""Everything you need to build your own CLI."""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from cliron._parents import argument, flag, option
    from cliron._roots import command, group

__all__ = [
    "__version__",
    "argument",
    "command",
    "flag",
    "group",
    "option",
]

__version__: str

_MODULES = {
    "argument": "cliron._parents",
    "command": "cliron._roots",
    "flag": "cliron._parents",
    "group": "cliron._roots",
    "option": "cliron._parents",
}


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})


def __getattr__(name: str) -> object:
    if name == "__version__":
        from importlib.metadata import version

        return version("cliron")
    if name in _MODULES:
        from importlib import import_module

        return cast("object", getattr(import_module(_MODULES[name]), name))
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
