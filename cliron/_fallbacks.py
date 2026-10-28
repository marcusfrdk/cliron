import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType
from typing import Literal

from cliron._children import Child, check_below
from cliron._names import check_variable, joined
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
    asks: bool = False

    def label(self) -> str | None:
        return None if self.variable is None else f"${self.variable}"

    def __call__(self, function: F) -> F:
        check_below(function, self.written)
        store(self, function, self.written)
        return function

    def __repr__(self) -> str:
        return self.written


def fallback(
    *,
    env: str | None = None,
    fn: Loader | ParentFactory | None = None,
    prompt: Literal[True] | str | None = None,
    hidden: bool = False,
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
    :param prompt: ``True`` to ask on the terminal, such as ``Api token:`` for
        ``api_token``, or the question to ask instead. It asks only when stdin
        is a terminal, never once the command line has errors, and an empty
        answer counts as no text.
    :param hidden: Whether the answer to ``prompt`` isn't shown as it's typed,
        as for a password.
    :returns: A decorator that goes below a parent, above its children.
    :raises TypeError: If it gets no source or more than one of ``env``,
        ``fn`` and ``prompt``, ``env`` isn't a string, ``fn`` isn't a function
        that takes the name as its only argument, ``prompt`` isn't ``True`` or
        a string, or ``hidden`` isn't a bool or comes without ``prompt``.
    :raises ValueError: If ``env`` isn't letters, digits and underscores that
        don't start with a digit, or ``prompt`` is empty.
    """
    variable = check_variable(env, "@fallback", "env")
    question = _check_prompt(prompt)
    _check_hidden(hidden, question)
    given = [
        name
        for name, source in [("env", variable), ("fn", fn), ("prompt", question)]
        if source is not None
    ]
    if len(given) > 1:
        message = (
            f"@fallback takes one source, but got {joined(given, 'and')}. "
            "Put each in its own @fallback."
        )
        raise TypeError(message)
    if variable is not None:
        return Fallback(
            lambda _: read_variable(variable), variable, f'fallback(env="{variable}")'
        )
    if question is not None:
        return _prompting(question, hidden=hidden)
    if fn is None:
        message = (
            '@fallback takes one source, such as @fallback(env="API_TOKEN") '
            "or @fallback(fn=git_branch)."
        )
        raise TypeError(message)
    loader = fn.function if isinstance(fn, ParentFactory) else fn
    name = check_loader(loader, "@fallback takes fn as", "fallback function")
    return Fallback(loader, None, f"fallback(fn={name})")


def _check_prompt(prompt: object) -> str | Literal[True] | None:
    if prompt is None or prompt is True:
        return prompt
    message = (
        '@fallback takes prompt as True or a question, such as prompt="Which '
        f'region?", not {prompt!r}.'
    )
    if not isinstance(prompt, str):
        raise TypeError(message)
    if not prompt.strip():
        raise ValueError(message)
    return prompt


def _check_hidden(hidden: object, question: object) -> None:
    if not isinstance(hidden, bool):
        message = f"@fallback takes hidden as True or False, not {hidden!r}."
        raise TypeError(message)
    if hidden and question is None:
        message = (
            "@fallback takes hidden only with prompt, such as "
            "@fallback(prompt=True, hidden=True)."
        )
        raise TypeError(message)


def _prompting(question: str | Literal[True], *, hidden: bool) -> Fallback:
    shown = "True" if question is True else f'"{question}"'
    written = f"fallback(prompt={shown}{', hidden=True' if hidden else ''})"

    def ask(name: str) -> str | None:
        stdin = sys.stdin
        if stdin is None or not stdin.isatty():
            return None
        asked = _question(name) if question is True else question
        try:
            return _answer(f"{asked} ", hidden=hidden) or None
        except EOFError:
            return None

    return Fallback(ask, None, written, asks=True)


def _question(name: str) -> str:
    return f"{name.removesuffix('_').replace('_', ' ').capitalize()}:"


def _answer(question: str, *, hidden: bool) -> str:
    if hidden and sys.stdin is sys.__stdin__:
        import getpass

        return getpass.getpass(question, stream=sys.stderr)
    _ = sys.stderr.write(question)
    _ = sys.stderr.flush()
    if not hidden:
        return input()
    return sys.stdin.readline().removesuffix("\n")


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
