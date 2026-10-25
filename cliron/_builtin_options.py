from collections.abc import Sequence
from dataclasses import dataclass

from cliron._names import check_flag


@dataclass(frozen=True)
class HelpOption:
    flags: tuple[str, ...]


@dataclass(frozen=True)
class VersionOption:
    version: str
    flags: tuple[str, ...] = ("--version",)


@dataclass(frozen=True)
class Builtins:
    help: HelpOption
    version: VersionOption | None

    @property
    def flags(self) -> dict[str, str]:
        found = dict.fromkeys(self.help.flags, "help")
        if self.version is not None:
            found.update(dict.fromkeys(self.version.flags, "version"))
        return found


DEFAULT_BUILTINS = Builtins(HelpOption(("-h", "--help")), None)


def help_option_for(help_flags: object, decorator: str) -> HelpOption | None:
    if help_flags is True:
        return None
    if help_flags is False:
        return HelpOption(())
    if isinstance(help_flags, str) or not isinstance(help_flags, Sequence):
        message = (
            f"@{decorator} takes help_flags as True, False or a list of flags, "
            f'such as ["--help"], not {help_flags!r}.'
        )
        raise TypeError(message)
    flags: list[str] = []
    for flag in help_flags:
        checked = check_flag(flag, f"help_flags of @{decorator}")
        if checked in flags:
            message = f"help_flags of @{decorator} lists {checked} twice. Remove one."
            raise ValueError(message)
        flags.append(checked)
    return HelpOption(tuple(flags))


def version_option_for(version: object, decorator: str) -> VersionOption | None:
    if version is None:
        return None
    if isinstance(version, str):
        return VersionOption(version)
    message = (
        f'@{decorator} takes version as a string, such as "1.4.0", not {version!r}.'
    )
    raise TypeError(message)
