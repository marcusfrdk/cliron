import inspect
import os
import re
from collections.abc import Sequence
from typing import TextIO, cast

from cliron._builtin_options import Builtins
from cliron._conversion import shown
from cliron._names import placeholder
from cliron._parents import Env, Flag, Option, Stdin
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


def render_help(nodes: Sequence[Node], builtins: Builtins, width: int) -> str:
    node = nodes[-1]
    definition = node.definition()
    sections = [_usage(nodes, width)]
    summary = _summary(node)
    if summary:
        sections.append(_fill(summary, width))
    arguments = [
        _value_row(_placeholder(target), target, show_required=False)
        for target in definition.arguments
    ]
    options = [_option_row(target) for target in _own_options(node)]
    if builtins.version is not None:
        options.append(
            (", ".join(builtins.version.flags), "Show the version and exit.")
        )
    options.append((", ".join(builtins.help.flags), "Show this help and exit."))
    commands = [(key, _first_line(command)) for key, command in node.commands.items()]
    tables = [("Arguments", arguments), ("Options", options)]
    for index, group in enumerate(nodes[:-1]):
        rows = [_option_row(target) for target in _own_options(group)]
        tables.append((f"Options for {node_path(nodes[: index + 1])}", rows))
    environment = [
        _value_row(target.parent.variable, target, show_required=True)
        for each in nodes
        for target in each.definition().inputs
        if isinstance(target.parent, Env)
    ]
    piped = [
        _value_row(target.display, target, show_required=True)
        for target in definition.inputs
        if isinstance(target.parent, Stdin)
    ]
    tables.extend([("Environment", environment), ("Input", piped)])
    position = _help_position(
        [*(row for _, rows in tables for row in rows), *commands], width
    )
    sections.extend(_tables(tables, position, width))
    sections.extend(_dependency_sections(nodes, width))
    sections.extend(_tables([("Commands", commands)], position, width))
    return "\n\n".join(sections) + "\n"


def _tables(
    tables: list[tuple[str, list[tuple[str, str]]]], position: int, width: int
) -> list[str]:
    return [
        "\n".join([f"{title}:", *_table(rows, position, width)])
        for title, rows in tables
        if rows
    ]


def _dependency_sections(nodes: Sequence[Node], width: int) -> list[str]:
    titled = [
        ("Dependencies", nodes[-1]),
        *(
            (f"Dependencies for {node_path(nodes[: index + 1])}", group)
            for index, group in enumerate(nodes[:-1])
        ),
    ]
    sections: list[str] = []
    for title, node in titled:
        definition = node.definition()
        label = definition.labels.__getitem__
        lines = [
            _fill(found.sentence(label), width, indent=4, first_indent=2)
            for found in definition.dependencies
        ]
        if lines:
            sections.append("\n".join([f"{title}:", *lines]))
    return sections


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


def _usage(nodes: Sequence[Node], width: int) -> str:
    node = nodes[-1]
    parts = ["Usage:"]
    for group in nodes[:-1]:
        parts.append(node_path([group]))
        if _own_options(group):
            parts.append("[OPTIONS]")
    parts.extend((node_path([node]), "[OPTIONS]"))
    if node.kind == "group":
        parts.append("COMMAND")
    for target in node.definition().arguments:
        name = _placeholder(target)
        parts.append(name if target.required else f"[{name}]")
    return _fill(" ".join(parts), width, indent=len("Usage: "))


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


def _value_row(name: str, target: Input, *, show_required: bool) -> tuple[str, str]:
    if target.converter is not None and target.converter.choices:
        name += f" {target.converter.metavar}"
    return name, _describe(target, show_required=show_required)


def _option_row(target: Input) -> tuple[str, str]:
    parent = target.parent
    names = [target.display]
    if isinstance(parent, Option | Flag) and parent.short is not None:
        names.insert(0, parent.short)
    invocation = ", ".join(names)
    if target.converter is not None:
        invocation += f" {target.converter.metavar}"
    return invocation, _describe(target, show_required=True)


def _describe(target: Input, *, show_required: bool) -> str:
    parts = [_words(target.parent.help or "")]
    parts.extend(
        sentence for child in target.children if (sentence := child.sentence())
    )
    if target.multiple or target.counted:
        piped = isinstance(target.parent, Stdin)
        parts.append("One per line." if piped else "Repeatable.")
    if target.required:
        parts.append("(required)" if show_required else "")
    elif target.converter is not None:
        default = _format_default(target.default)
        if default is not None:
            parts.append(f"(default: {default})")
    return " ".join(part for part in parts if part)


def _format_default(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        items = [_format_default(item) for item in cast("Sequence[object]", value)]
        return ", ".join(item for item in items if item is not None) or None
    return shown(value)


def _help_position(rows: list[tuple[str, str]], width: int) -> int:
    longest = max(len(left) for left, _ in rows)
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
