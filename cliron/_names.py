import keyword
import re
from collections.abc import Iterable, Sequence

_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")
_SHORT_FLAG = re.compile(r"-[A-Za-z]")
_LONG_FLAG = re.compile(r"--[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def check_name(name: object, decorator: str) -> str:
    text = _text(name, decorator)
    if is_snake_case(text):
        return text
    raise ValueError(_not_snake_case(text, snake_case(text)))


def check_aliases(
    aliases: object, name: str, caller: str, kind: str
) -> tuple[str, ...]:
    if isinstance(aliases, str):
        return (_check_alias(aliases, name, kind),)
    if not isinstance(aliases, Sequence):
        raise TypeError(_not_aliases(aliases, caller))
    checked: list[str] = []
    for alias in aliases:
        if not isinstance(alias, str):
            raise TypeError(_not_aliases(aliases, caller))
        if _check_alias(alias, name, kind) in checked:
            message = f"aliases of {caller} lists {alias!r} twice. Remove one."
            raise ValueError(message)
        checked.append(alias)
    return tuple(checked)


def _check_alias(alias: str, name: str, kind: str) -> str:
    if not is_snake_case(alias):
        raise ValueError(_not_snake_case(alias, snake_case(alias)))
    if alias == name:
        message = f"{alias!r} is already the {kind}'s name. Remove it from aliases."
        raise ValueError(message)
    return alias


def check_help(help: object, caller: str) -> str | None:
    if help is None or isinstance(help, str):
        return help
    message = (
        f'{caller} takes help as a string, such as help="How many.", not {help!r}.'
    )
    raise TypeError(message)


def check_parameter_name(name: object, decorator: str) -> str:
    text = _text(name, decorator)
    if keyword.iskeyword(text):
        message = (
            f"{text!r} is a Python keyword, so no parameter can have that name. "
            f"Use {text + '_'!r}: users don't type the trailing underscore."
        )
        raise ValueError(message)
    if is_parameter_name(text):
        return text
    raise ValueError(_not_snake_case(text, parameter_suggestion(text)))


def is_snake_case(name: str) -> bool:
    return _SNAKE_CASE.fullmatch(name) is not None


def is_parameter_name(name: str) -> bool:
    return is_snake_case(name.removesuffix("_"))


def snake_case(name: str) -> str | None:
    suggestion = "_".join(_WORD.findall(name)).lower()
    return suggestion if name.isascii() and is_snake_case(suggestion) else None


def parameter_suggestion(name: str) -> str | None:
    suggestion = snake_case(name)
    if suggestion is not None and keyword.iskeyword(suggestion):
        return f"{suggestion}_"
    return suggestion


def check_short(short: object, decorator: str) -> str | None:
    if short is not None and not isinstance(short, str):
        message = (
            f"@{decorator} takes the short flag as a string, such as '-c', "
            f"not {short!r}. A default value goes in the function's signature."
        )
        raise TypeError(message)
    if short is None or _SHORT_FLAG.fullmatch(short):
        return short
    message = f"{short!r} isn't a short flag. Use a dash and one letter, such as '-c'."
    raise ValueError(message)


def check_flag(flag: object, context: str) -> str:
    if not isinstance(flag, str):
        message = f"{context} takes flags as strings, such as '--help', not {flag!r}."
        raise TypeError(message)
    if _SHORT_FLAG.fullmatch(flag) or _LONG_FLAG.fullmatch(flag):
        return flag
    message = (
        f"{flag!r} isn't a flag. Use a dash and one letter, such as '-h', "
        "or two dashes and a kebab-case name, such as '--help'."
    )
    raise ValueError(message)


def check_variable(variable: object) -> str | None:
    if variable is not None and not isinstance(variable, str):
        message = (
            "@env takes variable as a string, such as "
            f'variable="GITHUB_TOKEN", not {variable!r}.'
        )
        raise TypeError(message)
    if variable is None or _VARIABLE.fullmatch(variable):
        return variable
    message = (
        f"{variable!r} isn't an environment variable name. Use letters, digits "
        "and underscores, not starting with a digit, such as 'GITHUB_TOKEN'."
    )
    raise ValueError(message)


def closest(word: str, candidates: Iterable[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(word, list(candidates), n=1)
    return matches[0] if matches else None


def token(name: str) -> str:
    return name.removesuffix("_").replace("_", "-")


def long_flag(name: str) -> str:
    return f"--{token(name)}"


def placeholder(name: str) -> str:
    return name.removesuffix("_").upper()


def _text(name: object, decorator: str) -> str:
    if isinstance(name, str):
        return name
    message = f'@{decorator} needs a name in parentheses, such as @{decorator}("name").'
    raise TypeError(message)


def _not_aliases(aliases: object, caller: str) -> str:
    return (
        f"{caller} takes aliases as a name or a list of names, "
        f"such as 'ls' or ['ls', 'l'], not {aliases!r}."
    )


def _not_snake_case(name: str, suggestion: str | None) -> str:
    if suggestion is None:
        return (
            f"{name!r} isn't snake_case. A name starts with a lowercase letter "
            "and contains only lowercase letters, digits and single underscores."
        )
    return f"{name!r} isn't snake_case. Use {suggestion!r}."
