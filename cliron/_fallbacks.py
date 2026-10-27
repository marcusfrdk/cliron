from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType

from cliron._children import Child, check_below
from cliron._names import check_variable
from cliron._nodes import F, nodes_of, store
from cliron._parents import (
    Flag,
    Loader,
    Parent,
    ParentFactory,
    call,
    check_loader,
    read_variable,
)


@dataclass(frozen=True, repr=False)
class Fallback:
    load: Loader
    variable: str | None
    written: str

    def label(self) -> str | None:
        return None if self.variable is None else f"${self.variable}"

    def __call__(self, function: F) -> F:
        check_below(function, self.written)
        store(self, function, self.written)
        return function

    def __repr__(self) -> str:
        return self.written


def fallback(
    *, env: str | None = None, fn: Loader | ParentFactory | None = None
) -> Callable[[F], F]:
    """
    Fill the parameter of the parent above when that parent has no value.

    It goes below the parent, above the parent's children, and takes one
    source. After the parent, each ``@fallback`` is tried top-down, and the
    first one with text gives the value. Its text is converted and checked by
    the children like the parent's own. If none has text, the parameter's
    default is used.

    :param env: The environment variable to read, such as ``"API_TOKEN"``. A
        variable that is set to an empty value counts as not set.
    :param fn: A function that takes the parameter's name and returns its
        text, or ``None`` if there is none, like the function of ``@parent``.
        It may be ``async def``, or decorated with ``@parent``.
    :returns: A decorator that goes below a parent, above its children.
    :raises TypeError: If it gets neither or both of ``env`` and ``fn``,
        ``env`` isn't a string, or ``fn`` isn't a function that takes the name
        as its only argument.
    :raises ValueError: If ``env`` isn't letters, digits and underscores that
        don't start with a digit.
    """
    variable = check_variable(env, "@fallback", "env")
    if variable is not None:
        if fn is not None:
            message = (
                "@fallback takes one source, but got both env and fn. "
                "Put each in its own @fallback."
            )
            raise TypeError(message)
        return Fallback(
            lambda _: read_variable(variable), variable, f'fallback(env="{variable}")'
        )
    if fn is None:
        message = (
            '@fallback takes one source, such as @fallback(env="API_TOKEN") '
            "or @fallback(fn=git_branch)."
        )
        raise TypeError(message)
    loader = fn.function if isinstance(fn, ParentFactory) else fn
    name = check_loader(loader, "@fallback takes fn as", "fallback function")
    return Fallback(loader, None, f"fallback(fn={name})")


def fallbacks_of(function: FunctionType) -> dict[str, tuple[Fallback, ...]]:
    attached: dict[str, list[Fallback]] = {}
    above: Parent | None = None
    first_child: object = None
    for record in nodes_of(function):
        if isinstance(record, Parent):
            above, first_child = record, None
        elif isinstance(record, Child) and first_child is None:
            first_child = record
        elif isinstance(record, Fallback):
            name = _owner(record, above, first_child)
            attached.setdefault(name, []).append(record)
    return {name: tuple(found) for name, found in attached.items()}


def _owner(found: Fallback, above: Parent | None, first_child: object) -> str:
    if above is None:
        message = (
            f"@{found!r} is above every parent, so it has nothing to fall back "
            "for. Put it right below the parent whose value it gives."
        )
        raise TypeError(message)
    if isinstance(above, Flag):
        message = (
            f"{call(above)} can't have a fallback, because a flag has no text. "
            f"Remove @{found!r}."
        )
        raise TypeError(message)
    if first_child is not None:
        message = (
            f"@{found!r} is below @{first_child!r}, but fallbacks come before "
            f"children. Move it above @{first_child!r}."
        )
        raise TypeError(message)
    return above.name
