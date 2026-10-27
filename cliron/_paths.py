from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from cliron._children import Child

Kind = Literal["file", "directory"]


@dataclass(frozen=True, repr=False)
class PathCheck(Child[Path, Path]):
    kind: Kind
    exists: bool | None

    default_check: ClassVar[Literal["definition", "run"]] = "run"

    def process(self, value: Path, /) -> Path:
        quoted = f"'{value}'"
        if not value.exists():
            if self.exists:
                message = f"{quoted} doesn't exist."
                raise ValueError(message)
            return value
        if self.exists is False:
            message = f"{quoted} already exists."
            raise ValueError(message)
        if value.is_dir() != (self.kind == "directory"):
            message = (
                f"{quoted} is a directory, not a file."
                if self.kind == "file"
                else f"{quoted} isn't a directory."
            )
            raise ValueError(message)
        return value

    def describe(self) -> str:
        if self.exists is None:
            return (
                "Must not be a directory."
                if self.kind == "file"
                else "Must be a directory if it exists."
            )
        if self.exists:
            return f"Must be an existing {self.kind}."
        return "Must not exist yet."

    def __repr__(self) -> str:
        options = "" if self.exists is True else f"exists={self.exists}"
        return f"{self.kind}({options})"


def file(*, exists: bool | None = True) -> Child[Path, Path]:
    """
    Check that the path above is a file.

    Anything but a directory counts as a file, such as ``/dev/null``. The check
    follows symbolic links, and runs on each run that uses the default, too.

    :param exists: ``True`` if the file must exist, ``False`` if nothing may be
        there yet, or ``None`` if either is fine.
    :returns: A decorator that goes below the parent whose path it checks.
    :raises TypeError: If ``exists`` isn't ``True``, ``False`` or ``None``.
    """
    return _path_check("file", exists)


def directory(*, exists: bool | None = True) -> Child[Path, Path]:
    """
    Check that the path above is a directory.

    The check follows symbolic links, and runs on each run that uses the
    default, too.

    :param exists: ``True`` if the directory must exist, ``False`` if nothing
        may be there yet, or ``None`` if either is fine.
    :returns: A decorator that goes below the parent whose path it checks.
    :raises TypeError: If ``exists`` isn't ``True``, ``False`` or ``None``.
    """
    return _path_check("directory", exists)


def _path_check(kind: Kind, exists: object) -> PathCheck:
    if exists is not None and not isinstance(exists, bool):
        message = f"@{kind} takes exists=True, False or None, not {exists!r}."
        raise TypeError(message)
    return PathCheck(kind, exists)
