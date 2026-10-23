"""Everything you need to build your own CLI."""

__all__ = ["__version__"]

__version__: str


def __getattr__(name: str) -> str:
    if name == "__version__":
        from importlib.metadata import version

        return version("cliron")
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
