"""Everything you need to build your own CLI."""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from cliron._children import Child, between, child, choices, length, matches
    from cliron._context import Context, state
    from cliron._dependencies import dependency
    from cliron._parents import Parent, argument, env, flag, option, parent, stdin
    from cliron._paths import directory, file
    from cliron._roots import command, group

__all__ = [
    "Child",
    "Context",
    "Parent",
    "__version__",
    "argument",
    "between",
    "child",
    "choices",
    "command",
    "dependency",
    "directory",
    "env",
    "file",
    "flag",
    "group",
    "length",
    "matches",
    "option",
    "parent",
    "state",
    "stdin",
]

__version__: str

_MODULES = {
    "Child": "cliron._children",
    "Context": "cliron._context",
    "Parent": "cliron._parents",
    "argument": "cliron._parents",
    "between": "cliron._children",
    "child": "cliron._children",
    "choices": "cliron._children",
    "command": "cliron._roots",
    "dependency": "cliron._dependencies",
    "directory": "cliron._paths",
    "env": "cliron._parents",
    "file": "cliron._paths",
    "flag": "cliron._parents",
    "group": "cliron._roots",
    "length": "cliron._children",
    "matches": "cliron._children",
    "option": "cliron._parents",
    "parent": "cliron._parents",
    "state": "cliron._context",
    "stdin": "cliron._parents",
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
