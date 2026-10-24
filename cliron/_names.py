import keyword
import re

_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")
_SHORT_FLAG = re.compile(r"-[A-Za-z]")


def check_name(name: object, decorator: str) -> str:
    text = _text(name, decorator)
    if is_snake_case(text):
        return text
    raise ValueError(_not_snake_case(text, snake_case(text)))


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


def check_short(short: object) -> str | None:
    if short is not None and not isinstance(short, str):
        message = (
            f"the short flag must be a string such as '-c', not {short!r}. "
            "A default value goes in the function's signature."
        )
        raise TypeError(message)
    if short is None or _SHORT_FLAG.fullmatch(short):
        return short
    message = f"{short!r} isn't a short flag. Use a dash and one letter, such as '-c'."
    raise ValueError(message)


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


def _not_snake_case(name: str, suggestion: str | None) -> str:
    if suggestion is None:
        return (
            f"{name!r} isn't snake_case. A name starts with a lowercase letter "
            "and contains only lowercase letters, digits and single underscores."
        )
    return f"{name!r} isn't snake_case. Use {suggestion!r}."
