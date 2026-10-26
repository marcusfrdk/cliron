import inspect
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, TextIO, cast

from cliron._builtin_options import Builtins
from cliron._conversion import shown
from cliron._names import long_flag, placeholder
from cliron._parents import CommandLineParent, Env, Flag, Option, Stdin
from cliron._parsing import Input, Node, node_path

_MAX_WIDTH = 80
_MARGIN = 2
_INDENT = 2
_GAP = 2
_MAX_HELP_POSITION = 24
_MIN_HELP_WIDTH = 11
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_BREAKABLE_SPACE = re.compile(r"[ \t\n\r\f\v]+")


def usage_hint(nodes: Sequence[Node], builtins: Builtins) -> str | None:
    if not builtins.help.flags:
        return None
    flag = next(
        (flag for flag in builtins.help.flags if flag.startswith("--")),
        builtins.help.flags[0],
    )
    return f"Run '{node_path(nodes)} {flag}' for usage."


SectionKind = Literal[
    "arguments", "options", "environment", "input", "dependencies", "commands"
]


@dataclass(frozen=True)
class HelpRow:
    names: tuple[str, ...]
    value: str | None = None
    text: str = ""
    notes: tuple[str, ...] = ()
    default: str | None = None
    required: bool = False


@dataclass(frozen=True)
class HelpSection:
    kind: SectionKind
    title: str
    rows: tuple[HelpRow, ...]


@dataclass(frozen=True)
class Help:
    usage: tuple[str, ...]
    summary: str
    sections: tuple[HelpSection, ...]


def render_help(nodes: Sequence[Node], builtins: Builtins, width: int) -> str:
    return render(help_for(nodes, builtins), width)


def help_for(nodes: Sequence[Node], builtins: Builtins) -> Help:
    node = nodes[-1]
    definition = node.definition()
    options = [_option_row(target) for target in _own_options(node)]
    if builtins.version is not None:
        options.append(
            HelpRow(builtins.version.flags, text="Show the version and exit.")
        )
    options.append(HelpRow(builtins.help.flags, text="Show this help and exit."))
    sections = [
        _section(
            "arguments",
            "Arguments",
            [
                _value_row(_placeholder(target), target)
                for target in definition.arguments
            ],
        ),
        _section("options", "Options", options),
        *(
            _section(
                "options",
                f"Options for {node_path(nodes[: index + 1])}",
                [_option_row(target) for target in _own_options(group)],
            )
            for index, group in enumerate(nodes[:-1])
        ),
        _section(
            "environment",
            "Environment",
            [
                _value_row(target.parent.variable, target)
                for each in nodes
                for target in each.definition().inputs
                if isinstance(target.parent, Env)
            ],
        ),
        _section(
            "input",
            "Input",
            [
                _value_row(target.display, target)
                for each in nodes
                for target in each.definition().inputs
                if not isinstance(target.parent, CommandLineParent | Env)
            ],
        ),
        _dependencies("Dependencies", node),
        *(
            _dependencies(f"Dependencies for {node_path(nodes[: index + 1])}", group)
            for index, group in enumerate(nodes[:-1])
        ),
        _section(
            "commands",
            "Commands",
            [
                HelpRow((key,), text=_first_line(command))
                for key, command in node.commands.items()
            ],
        ),
    ]
    return Help(
        _usage(nodes),
        _summary(node),
        tuple(section for section in sections if section.rows),
    )


def render(help: Help, width: int) -> str:
    blocks = [_fill(" ".join(["Usage:", *help.usage]), width, indent=len("Usage: "))]
    if help.summary:
        blocks.append(_fill(help.summary, width))
    terms = [
        _term(row)
        for section in help.sections
        if section.kind != "dependencies"
        for row in section.rows
    ]
    position = _help_position(terms, width)
    for section in help.sections:
        if section.kind == "dependencies":
            lines = [
                _fill(row.text, width, indent=4, first_indent=2) for row in section.rows
            ]
        else:
            rows = [(_term(row), _description(row, section)) for row in section.rows]
            lines = _table(rows, position, width)
        blocks.append("\n".join([f"{section.title}:", *lines]))
    return "\n\n".join(blocks) + "\n"


def _section(kind: SectionKind, title: str, rows: list[HelpRow]) -> HelpSection:
    return HelpSection(kind, title, tuple(rows))


def _dependencies(title: str, node: Node) -> HelpSection:
    definition = node.definition()
    label = definition.labels.__getitem__
    rows = [
        HelpRow((), text=_words(found.sentence(label)))
        for found in definition.dependencies
    ]
    return _section("dependencies", title, rows)


def terminal_width(stream: TextIO) -> int:
    columns = os.environ.get("COLUMNS", "")
    if columns.isdecimal() and int(columns) > 0:
        width = int(columns)
    else:
        try:
            width = os.get_terminal_size(stream.fileno()).columns
        except (AttributeError, OSError, ValueError):
            width = 0
    return max(min(width or _MAX_WIDTH, _MAX_WIDTH) - _MARGIN, 1)


def _usage(nodes: Sequence[Node]) -> tuple[str, ...]:
    node = nodes[-1]
    words: list[str] = []
    for group in nodes[:-1]:
        words.append(node_path([group]))
        if _own_options(group):
            words.append("[OPTIONS]")
    words.extend((node_path([node]), "[OPTIONS]"))
    if node.kind == "group":
        words.append("COMMAND")
    for target in node.definition().arguments:
        name = _placeholder(target)
        words.append(name if target.required else f"[{name}]")
    return tuple(words)


def _summary(node: Node) -> str:
    docstring = inspect.cleandoc(node.function.__doc__ or "").strip()
    return _PARAGRAPH_BREAK.split(docstring)[0]


def _first_line(node: Node) -> str:
    return _summary(node).split("\n")[0]


def _own_options(node: Node) -> list[Input]:
    return [
        target
        for target in node.definition().inputs
        if isinstance(target.parent, Option | Flag)
    ]


def _placeholder(target: Input) -> str:
    return placeholder(target.name) + ("..." if target.multiple else "")


def _value_row(name: str, target: Input) -> HelpRow:
    converter = target.converter
    value = converter.metavar if converter is not None and converter.choices else None
    return _row((name,), value, target)


def _option_row(target: Input) -> HelpRow:
    parent = target.parent
    names = [long_flag(target.name)]
    if isinstance(parent, Option | Flag) and parent.short is not None:
        names.insert(0, parent.short)
    value = None if target.converter is None else target.converter.metavar
    return _row(tuple(names), value, target)


def _row(names: tuple[str, ...], value: str | None, target: Input) -> HelpRow:
    notes = [sentence for child in target.children if (sentence := child.describe())]
    if target.multiple or target.counted:
        piped = isinstance(target.parent, Stdin)
        notes.append("One per line." if piped else "Repeatable.")
    default = (
        None
        if target.required or target.converter is None
        else _format_default(target.default)
    )
    return HelpRow(
        names,
        value,
        _words(target.parent.help or ""),
        tuple(notes),
        default,
        target.required,
    )


def _term(row: HelpRow) -> str:
    names = ", ".join(row.names)
    return names if row.value is None else f"{names} {row.value}"


def _description(row: HelpRow, section: HelpSection) -> str:
    parts = [row.text, *row.notes]
    if row.required and section.kind != "arguments":
        parts.append("(required)")
    elif not row.required and row.default is not None:
        parts.append(f"(default: {row.default})")
    return " ".join(part for part in parts if part)


def _format_default(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        items = [_format_default(item) for item in cast("Sequence[object]", value)]
        return ", ".join(item for item in items if item is not None) or None
    return shown(value)


def _help_position(terms: list[str], width: int) -> int:
    longest = max((len(term) for term in terms), default=0)
    return min(
        longest + _INDENT + _GAP,
        _MAX_HELP_POSITION,
        max(width - 20, _INDENT * 2),
    )


def _table(rows: list[tuple[str, str]], position: int, width: int) -> list[str]:
    import textwrap

    help_width = max(width - position, _MIN_HELP_WIDTH)
    lines: list[str] = []
    for left, right in rows:
        wrapped = textwrap.wrap(
            right, help_width, break_on_hyphens=False, break_long_words=False
        )
        head = " " * _INDENT + left
        if wrapped and len(head) + _GAP <= position:
            lines.append(head.ljust(position) + wrapped[0])
            wrapped = wrapped[1:]
        else:
            lines.append(head)
        lines.extend(" " * position + line for line in wrapped)
    return lines


def _fill(text: str, width: int, indent: int = 0, first_indent: int = 0) -> str:
    import textwrap

    return textwrap.fill(
        _words(text),
        width,
        initial_indent=" " * first_indent,
        subsequent_indent=" " * indent,
        break_on_hyphens=False,
        break_long_words=False,
    )


def _words(text: str) -> str:
    return _BREAKABLE_SPACE.sub(" ", text).strip()
