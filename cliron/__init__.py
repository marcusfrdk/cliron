"""Everything you need to build your own CLI."""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from cliron._children import between, choices, length, matches
    from cliron._dependencies import dependency
    from cliron._parents import argument, env, flag, option, stdin
    from cliron._roots import command, group

__all__ = [
    "__version__",
    "argument",
    "between",
    "choices",
    "command",
    "dependency",
    "env",
    "flag",
    "group",
    "length",
    "matches",
    "option",
    "stdin",
]

__version__: str

_MODULES = {
    "argument": "cliron._parents",
    "between": "cliron._children",
    "choices": "cliron._children",
    "command": "cliron._roots",
    "dependency": "cliron._dependencies",
    "env": "cliron._parents",
    "flag": "cliron._parents",
    "group": "cliron._roots",
    "length": "cliron._children",
    "matches": "cliron._children",
    "option": "cliron._parents",
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
