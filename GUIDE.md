# Guide

This is a guide showing you how to use the cliron framework. For more details about the API, see the [reference](REFERENCE.md) instead.

1. [Your first CLI](#1-your-first-cli)
2. [Running your CLI](#2-running-your-cli)
3. [How it works](#3-how-it-works)
4. [Taking input](#4-taking-input)
5. [Checking input](#5-checking-input)
6. [Commands and groups](#6-commands-and-groups)
7. [Running a command](#7-running-a-command)
8. [Testing](#8-testing)
9. [Shell completion](#9-shell-completion)
10. [Measuring](#10-measuring)

## 1. Your first CLI

```python
from cliron import argument, command, option


@command("greet")
@argument("name")
@option("greeting")
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone."""
    return f"{greeting}, {name}!"


if __name__ == "__main__":
    greet()
```

```console
$ python greet.py Ada
Hello, Ada!
$ python greet.py Ada --greeting Hi
Hi, Ada!
$ python greet.py --help
Usage: greet [OPTIONS] NAME

Greet someone.

Arguments:
  NAME

Options:
  --greeting TEXT  (default: Hello)
  -h, --help       Show this help and exit.
```

A command succeeds by returning and fails by raising:

| Your function                              | Writes                           | Exit code |
| ------------------------------------------ | -------------------------------- | --------- |
| `return "Added milk."`                     | `Added milk.` to stdout          | 0         |
| `raise SystemExit("There's no notes.db.")` | `There's no notes.db.` to stderr | 1         |

Output and errors stay apart, so `python notes.py > notes.txt` saves only the output. A string is written as it is, and a number, list or dict as JSON. A function that returns nothing writes nothing. [Exit codes](#exit-codes) lists the rest.

## 2. Running your CLI

While you write it, run the file with Python, as above. To run it by name, as `greet Ada`, make its folder a project:

```text
greet/
├── greet.py
└── pyproject.toml
```

```toml
[project]
name = "greet"
version = "0.1.0"
dependencies = ["cliron"]

[project.scripts]
greet = "greet:greet"

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
```

The line under `[project.scripts]` makes the command `greet` run `greet` from `greet.py`. Then install it from the `greet` folder:

| To run it                      | Install it with                |
| ------------------------------ | ------------------------------ |
| From your virtual environment  | `pip install --editable .`     |
| From anywhere on your computer | `uv tool install --editable .` |

```console
$ greet Ada
Hello, Ada!
```

## 3. How it works

A command is a function with decorators. Each decorator is one of four kinds:

| Kind     | Decorators                                                                              | What it does                                            |
| -------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Parent   | `@argument`, `@option`, `@flag`, `@env`, `@stdin`, your own `@parent`                   | Gives one parameter its text                            |
| Fallback | `@fallback`                                                                             | Gives the text when the parent above it has none        |
| Child    | `@between`, `@length`, `@matches`, `@choices`, `@file`, `@directory`, your own `@child` | Checks or changes the value of the parent above it      |
| Hook     | `@hook`                                                                                 | Runs a function around the command, or handles an error |

Python applies decorators bottom-up, but cliron reads them top-down, in the order they're written, which is the order things happen. A fallback or child belongs to the nearest parent above it, and a hook to the nearest command, group, parent or child above it. A decorator in a place it can't belong is an error that says where to move it.

```text
@command("add")
├── @hook(on.exit(), log)
├── @argument("text")
│   └── @length(1, 280)
└── @option("tag")
    ├── @fallback(env="NOTES_TAG")
    └── @matches(r"[a-z]+")
```

For each parameter, cliron:

1. Takes the parent's text, or else the first fallback's that has some.
2. With no text, uses the parameter's default, or reports the input as missing.
3. Converts the text to the parameter's annotation.
4. Runs each child, top-down, each one on what the one above returned.

Every input is read and checked before any group or command runs, or any hook around one. If any is invalid, every problem is listed at once, and none of them runs. An error hook below a parent or child is part of reading the inputs, as [Handling errors](#handling-errors) shows.

| A mistake                                                                                                                         | Is found                                                    |
| --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| A decorator in the wrong place, such as a child above every parent                                                                | When the module is imported                                 |
| A parameter without a decorator, a type cliron can't convert, arguments in an order that can't work, or a default a child rejects | When the command first runs, or by [`validate`](#8-testing) |
| Invalid input                                                                                                                     | On every run, with exit code 2                              |

## 4. Taking input

### Arguments

Arguments are filled in the order of their decorators. A `list` argument takes every remaining word.

```python
from cliron import argument, command


@command("tag")
@argument("text")
@argument("tags")
def tag(text: str, tags: list[str]) -> str:
    """Tag a note."""
    return f"Tagged {text!r} with {', '.join(tags)}."


if __name__ == "__main__":
    tag()
```

```console
$ python notes.py milk home shopping
Tagged 'milk' with home, shopping.
$ python notes.py -- -milk home
Tagged '-milk' with home.
```

| Rule                                         |                                                                                   |
| -------------------------------------------- | --------------------------------------------------------------------------------- |
| A `list` or `tuple` argument comes last      | It takes every remaining word                                                     |
| Required arguments come before optional ones | Otherwise a word couldn't tell which it fills                                     |
| After `--`, every word is an argument        | Even one that starts with `-`. In a group, the command's name can still follow it |

### Options and flags

| Decorator                | Users type                                        | Parameter              |
| ------------------------ | ------------------------------------------------- | ---------------------- |
| `@option("tag", "-t")`   | `--tag home`, `--tag=home`, `-t home` or `-thome` | `tag: str = "inbox"`   |
| `@flag("pinned", "-p")`  | `--pinned` or `-p`                                | `pinned: bool = False` |
| `@flag("verbose", "-v")` | `-vv` or `--verbose --verbose`                    | `verbose: int = 0`     |

```python
from cliron import argument, command, flag, option


@command("add")
@argument("text", help="What to write down.")
@option("tag", "-t", help="Where to file it.")
@flag("pinned", "-p", help="Keep it at the top.")
def add(text: str, tag: str = "inbox", pinned: bool = False) -> str:
    """Add a note."""
    where = "the top of " if pinned else ""
    return f"Added {text!r} to {where}{tag}."


if __name__ == "__main__":
    add()
```

```console
$ python notes.py milk -t shopping -p
Added 'milk' to the top of shopping.
$ python notes.py milk -t home -t work
error: -t/--tag can only be given once.
Run 'add --help' for usage.
$ python notes.py
error: TEXT is required.
Run 'add --help' for usage.
```

Options and arguments can come in any order. Short flags combine, so `-pv` is `-p -v`. A flag's parameter defaults to `False`, or to `0` to count it. An option annotated `list[str]` can be given several times. To type something other than the parameter's name, set `long`, so `@option("output_path", long="--output")` is `--output`.

### Types

The annotation sets the type:

| Annotation                 | Users type                                                                                         |
| -------------------------- | -------------------------------------------------------------------------------------------------- |
| `str`                      | Any text                                                                                           |
| `int`                      | A whole number, such as `3` or `-2`                                                                |
| `float`                    | A number, such as `2.5` or `1e3`                                                                   |
| `Path`                     | A path, which doesn't have to exist                                                                |
| `date`                     | `2026-10-27`                                                                                       |
| `datetime`                 | `2026-10-27 14:30` or `2026-10-27T14:30`                                                           |
| `time`                     | `14:30` or `14:30:15`                                                                              |
| `Literal["day", "week"]`   | One of the strings                                                                                 |
| An `Enum`                  | A member's name, in lowercase with `-` for `_`, so `DARK_RED` is `dark-red`                        |
| `list[X]`, `tuple[X, ...]` | Several values of a type above, from an option given several times or from the remaining arguments |
| `bool`                     | Only with `@flag`                                                                                  |

Dates and times are ISO 8601, as `date.fromisoformat` and its siblings read them.

```python
from datetime import date
from typing import Literal

from cliron import argument, command, option


@command("remind")
@argument("text")
@option("due")
@option("every")
def remind(text: str, due: date, every: Literal["day", "week"] = "week") -> str:
    """Remind me of something."""
    return f"{text}: from {due}, every {every}."


if __name__ == "__main__":
    remind()
```

```console
$ python notes.py "Water plants" --due 2026-11-01 --every day
Water plants: from 2026-11-01, every day.
$ python notes.py "Water plants" --due tomorrow --every month
error: --due: 'tomorrow' isn't a date (YYYY-MM-DD).
error: --every: 'month' isn't one of day, week.
Run 'remind --help' for usage.
```

### Required or optional

A default makes an input optional. It's used as it is, without being converted.

| Signature                      | When not given                       |
| ------------------------------ | ------------------------------------ |
| `due: date`                    | An error                             |
| `due: date = date(2026, 1, 1)` | `date(2026, 1, 1)`                   |
| `due: date \| None = None`     | `None`                               |
| `due: date \| None`            | An error, because there's no default |
| `tags: tuple[str, ...] = ()`   | `()`                                 |

Use a tuple, not a list, as the default of a list. A list default is one object, shared by every run in a process.

### From the environment or a pipe

```python
from pathlib import Path

from cliron import command, env, stdin


@command("import")
@env("notes_db", help="Where notes are kept.")
@stdin("lines")
def import_notes(lines: list[str], notes_db: Path = Path("notes.db")) -> str:
    """Add every line piped in as a note."""
    return f"{len(lines)} notes into {notes_db}."


if __name__ == "__main__":
    import_notes()
```

```console
$ printf 'milk\neggs\n' | python notes.py
2 notes into notes.db.
$ printf 'milk\neggs\n' | NOTES_DB=work.db python notes.py
2 notes into work.db.
```

`@env("notes_db")` reads `$NOTES_DB`, its name in capitals without a trailing `_`. `@env("token", variable="API_TOKEN")` reads another variable. A variable set to an empty value counts as not set. Help lists the variables under `Environment:`.

`@stdin` never reads from a terminal, so the program never waits for typing:

| Piped in                             | `lines: list[str]`       | `text: str`                                 |
| ------------------------------------ | ------------------------ | ------------------------------------------- |
| `milk`, `eggs`, each on its own line | `["milk", "eggs"]`       | `"milk\neggs"`, without the last line break |
| An empty pipe                        | `[]`                     | `""`                                        |
| Nothing, at a terminal               | The default, or an error | The default, or an error                    |

A command has at most one `@stdin`, and a group has none.

### When a value is missing

`@fallback` gives the text when the parent above it has none. Fallbacks are tried in the order they're written, then the default is used.

```python
from cliron import command, fallback, option


@command("sync")
@option("token")
@fallback(env="NOTES_TOKEN")
@fallback(prompt="Token:", hidden=True)
def sync(token: str) -> str:
    """Sync your notes."""
    return f"Synced with a {len(token)}-character token."


if __name__ == "__main__":
    sync()
```

```console
$ python notes.py --token abc
Synced with a 3-character token.
$ NOTES_TOKEN=abc123 python notes.py
Synced with a 6-character token.
$ echo | python notes.py
error: --token is required. It can also come from $NOTES_TOKEN.
Run 'sync --help' for usage.
```

At a terminal, it asks instead, without showing what you type:

```text
$ python notes.py
Token:
Synced with a 6-character token.
```

| Fallback                              | Gives                                                             |
| ------------------------------------- | ----------------------------------------------------------------- |
| `@fallback(env="NOTES_TOKEN")`        | The variable, unless it's not set or empty                        |
| `@fallback(fn=read_token)`            | The text `read_token("token")` returns, or `None` to try the next |
| `@fallback(prompt=True)`              | An answer typed at the terminal, asked as `Token:`                |
| `@fallback(prompt="Your token?")`     | The same, with your question                                      |
| `@fallback(prompt=True, hidden=True)` | The same, without showing the answer                              |

- A fallback's text is converted and checked like typed text. Errors about it name `$NOTES_TOKEN` for a variable, and the parent otherwise.
- Help and the missing-value error name only the variables.
- An argument with a fallback doesn't have to be typed, and usage shows it as `[TOKEN]`. Without a default, it's still an error when no fallback has text.
- A fallback goes right below its parent, above the parent's children. Flags and lists can't have one.

A prompt asks only when stdin is a terminal, and writes its question to stderr. An empty answer counts as no text, so the next fallback is tried. It doesn't ask once the command line has words that fit nowhere, or an input before it has failed.

A function fallback can read settings from a file, one setting per parameter:

```python
import tomllib
from pathlib import Path

from cliron import command, fallback, option

SETTINGS = Path.home() / ".notes.toml"


def setting(name: str) -> str | None:
    if not SETTINGS.exists():
        return None
    value = tomllib.loads(SETTINGS.read_text(encoding="utf-8")).get(name)
    return None if value is None else str(value)


@command("sync")
@option("server")
@fallback(env="NOTES_SERVER")
@fallback(fn=setting)
def sync(server: str = "notes.example.com") -> str:
    """Sync your notes."""
    return f"Synced with {server}."
```

### Custom parents

`@parent` turns a function into a parent like `@env`. The function gets the parameter's name and returns the text, or `None`.

```python
import subprocess

from cliron import command, parent


@parent
def git_branch(name: str) -> str | None:
    result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    return result.stdout.strip() or None


@command("deploy")
@git_branch("branch", help="The branch to deploy.")
def deploy(branch: str = "main") -> str:
    """Deploy a branch."""
    return f"Deploying {branch}."
```

Help lists it under `Input:`. To let users type `--branch` too, make it a fallback, with `@option("branch")` and then `@fallback(fn=git_branch)`.

For a parent with options of its own, subclass `Parent` and implement `load`, which reads `self.name`:

```python
from pathlib import Path

from cliron import Parent, command


class Secret(Parent):
    def __init__(self, name: str, folder: Path) -> None:
        super().__init__(name)
        self.folder = folder

    def load(self) -> str | None:
        path = self.folder / self.name
        return path.read_text(encoding="utf-8").strip() if path.exists() else None


@command("sync")
@Secret("token", Path("/run/secrets"))
def sync(token: str = "") -> str:
    """Sync your notes."""
    return "Synced." if token else "Not signed in."
```

## 5. Checking input

The children below a parent run after its text is converted, top-down, each on what the one above returned. The first one that fails stops that value. Each item of a list is checked on its own, and every input's problems are listed together.

### Built-in children

```python
from cliron import argument, between, choices, command, length, option


@command("add")
@argument("text")
@length(1, 280)
@option("priority")
@between(1, 5)
@option("color")
@choices("red", "green", "blue")
def add(text: str, priority: int = 3, color: str = "red") -> str:
    """Add a note."""
    return f"Added {text!r}, priority {priority}, {color}."


if __name__ == "__main__":
    add()
```

```console
$ python notes.py milk --priority 9 --color pink
error: --priority: 9 isn't between 1 and 5.
error: --color: 'pink' isn't one of red, green, blue.
Run 'add --help' for usage.
```

| Child                     | Accepts                                                                                                                | Help shows                       |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `@between(1, 5)`          | Numbers, dates or times from 1 to 5, both included. `between(low=1)` or `between(high=5)` leaves one side open         | `1 to 5.`                        |
| `@length(1, 280)`         | Text of 1 to 280 characters. `length(5)` is at least 5                                                                 | `1 to 280 characters.`           |
| `@matches(r"[a-z-]+")`    | Text the pattern matches as a whole                                                                                    | `Must match [a-z-]+.`            |
| `@choices("red", "blue")` | One of the values, of the parameter's type                                                                             | `[red\|blue]` in place of `TEXT` |
| `@file()`, `@directory()` | A `Path` to a file or directory that exists. With `exists=False`, nothing may be there yet. With `exists=None`, either | `Must be an existing file.`      |

### Custom children

A function decorated with `@child` checks or changes the value. Raise `ValueError` to reject it. Any other exception isn't caught.

```python
from cliron import argument, child, command


@child
def even(value: int) -> int:
    if value % 2:
        message = f"{value} isn't even."
        raise ValueError(message)
    return value


@child
def shout(text: str) -> str:
    return text.upper()


@command("pair")
@argument("count")
@even()
@argument("name")
@shout()
def pair(count: int, name: str) -> str:
    """Make pairs."""
    return f"{count // 2} pairs of {name}."


if __name__ == "__main__":
    pair()
```

```console
$ python notes.py 6 socks
3 pairs of SOCKS.
$ python notes.py 3 socks
error: COUNT: 3 isn't even.
Run 'pair --help' for usage.
```

The function's other parameters become the child's options, so `def at_most(value: int, limit: int) -> int` is used as `@at_most(limit=10)`.

A first child whose value is annotated `str`, below a parameter of another type, gets the text before it's converted. It does the converting, and returns the parameter's type:

```python
import json

from cliron import argument, child, command


@child
def parsed(text: str) -> dict[str, object]:
    return json.loads(text)


@command("tag")
@argument("data")
@parsed()
def tag(data: dict[str, object]) -> str:
    """Tag notes from JSON."""
    return f"Tagged with {sorted(data)}."


if __name__ == "__main__":
    tag()
```

```console
$ python notes.py '{"home": 1, "work": 2}'
Tagged with ['home', 'work'].
```

For a child with its own help sentence, subclass `Child`, and implement `process` and `describe`.

### Defaults

A default isn't typed, so children never change it. `@shout()` leaves a default of `"socks"` as it is. They do check it, once, when the command first runs or is validated, so `@between(1, 5)` with `priority: int = 9` is an error then, whatever users type. `@file`, `@directory` and async children check it on every run that uses it instead.

### Rules between inputs

```python
from cliron import command, dependency, flag, option


@command(
    "export",
    dependencies=[
        dependency.conflicts("json", "csv"),
        dependency.requires("password", "user"),
    ],
)
@flag("json")
@flag("csv")
@option("user")
@option("password")
def export(
    json: bool = False,
    csv: bool = False,
    user: str | None = None,
    password: str | None = None,
) -> str:
    """Export your notes."""
    return "Exported."


if __name__ == "__main__":
    export()
```

```console
$ python notes.py --json --csv --password secret
error: --json can't be used with --csv.
error: --password requires --user.
Run 'export --help' for usage.
```

| Rule                                     | Means                                                                                  |
| ---------------------------------------- | -------------------------------------------------------------------------------------- |
| `dependency.requires("a", "b")`          | With `a`, `b` is needed too                                                            |
| `dependency.requires_any("a", "b", "c")` | With `a`, `b` or `c` is needed too                                                     |
| `dependency.conflicts("a", "b", "c")`    | `a` can't be used with `b` or `c`                                                      |
| `dependency.together("a", "b")`          | Both or neither                                                                        |
| `dependency.alone("a")`                  | `a` can't be used with any other input, except ones from the environment or a fallback |
| `dependency.at_least(1, "a", "b")`       | At least one of them                                                                   |
| `dependency.at_most(1, "a", "b")`        | At most one of them                                                                    |
| `dependency.exactly(1, "a", "b")`        | Exactly one of them                                                                    |

Rules name inputs by their parameters. An input counts as given when it has text from anywhere, whether typed, piped, from the environment or from a fallback. A default never counts, so every input in a rule needs one. Groups take `dependencies=` too, for their own inputs. `validate` also finds rules that contradict each other.

## 6. Commands and groups

### Groups

```python
from cliron import argument, command, group


@group("notes")
def notes() -> None:
    """Keep notes."""


@command("add")
@argument("text")
def add(text: str) -> str:
    """Add a note."""
    return f"Added {text!r}."


@command("list", aliases="ls")
def list_notes() -> str:
    """List your notes."""
    return "milk, eggs"


notes.add(add, list_notes)

if __name__ == "__main__":
    notes()
```

```console
$ python notes.py add milk
Added 'milk'.
$ python notes.py ls
milk, eggs
$ python notes.py lst
error: 'lst' isn't a notes command. Did you mean 'list'?
Run 'notes --help' for usage.
$ python notes.py --help
Usage: notes [OPTIONS] COMMAND

Keep notes.

Options:
  -h, --help  Show this help and exit.

Commands:
  add         Add a note.
  list, ls    List your notes.
```

- `add` takes any number of commands and groups, and groups go inside groups the same way, with `notes.add(tags)`. A command can be in several groups.
- Users type names in kebab-case, so a command named `show_all` is `show-all`.
- A mistyped name suggests the closest name or alias.
- A group's name with nothing after it prints the group's help on stderr, with exit code 2.

A group's options go between its name and the command's, as in `notes --db work.db add milk` in [Setup and cleanup](#setup-and-cleanup). A command may have options with the same names as its group's.

### Hiding commands

`enabled=` takes a function. When it returns `False`, the command is left out of help, completion and suggestions, and running it says so.

```python
import os

from cliron import command, group


def is_admin() -> bool:
    return os.environ.get("NOTES_ROLE") == "admin"


@group("notes")
def notes() -> None:
    """Keep notes."""


@command("purge", enabled=is_admin)
def purge() -> str:
    """Delete every note."""
    return "Deleted every note."


notes.add(purge)

if __name__ == "__main__":
    notes()
```

```console
$ python notes.py purge
error: 'notes purge' is disabled.
Run 'notes --help' for usage.
$ NOTES_ROLE=admin python notes.py purge
Deleted every note.
```

A disabled group hides everything in it. The function is called each time cliron needs the answer, so keep it quick, such as reading a file once with `functools.cache`.

`enabled=` hides a command. It doesn't protect it, since anyone who can set `NOTES_ROLE` can run `purge`. Check permissions inside the command.

### Loading commands only when needed

A command with slow imports can wait until it's used. In a package:

```text
notes/
├── __init__.py
└── report.py
```

`notes/__init__.py` names the command and where it is, as `"module:attribute"`:

```py
notes.lazy("report", "notes.report:report", help="Build a report.")
```

| Imports `notes.report`                           | Doesn't                         |
| ------------------------------------------------ | ------------------------------- |
| `notes report`, `notes report --help`            | `notes --help`                  |
| `validate`                                       | Every other command             |
| Making the completion script, while it's enabled | Suggestions for a mistyped name |
| Completing one of its values                     |                                 |

The command it loads must have the same name, aliases and `enabled` function as `lazy` gave it.

### Help and version

| Write                                   | Shows                                                                                               |
| --------------------------------------- | --------------------------------------------------------------------------------------------------- |
| A docstring                             | Its first paragraph as the description, and that paragraph's first line in the group's list         |
| `help="..."` on a parent                | The parent's line                                                                                   |
| `version="1.4.0"` on a command or group | A `--version` flag for it and everything in it that doesn't set its own, which prints `notes 1.4.0` |
| `help_flags=["--usage"]`                | Other help flags                                                                                    |
| `help_flags=False`                      | No help flags                                                                                       |

### Calling from Python

`notes()` reads the command line in `sys.argv`, runs it, and exits with its exit code. To run a CLI with other words, as in a test, use [`cliron.testing.run`](#8-testing).

## 7. Running a command

### What happens, in order

For `notes --db work.db add milk`:

1. Every input of `notes` and `add` is read and checked, including prompts. If any is invalid, every problem is listed, and the run ends with exit code 2.
2. `notes` runs its start hooks, then its function up to `yield`.
3. `add` runs its start hooks, then its function.
4. `add` runs its error hooks if an exception left it, its success hooks if it succeeded or an error hook handled the exception, then its exit hooks.
5. `notes` runs the code after its `yield`, then its own error, success and exit hooks the same way.
6. The result is written to stdout.

### Setup and cleanup

A group's function runs before its command, and code after its `yield` runs after it. A `@state` class shares data between them.

```python
from collections.abc import Iterator
from pathlib import Path

from cliron import argument, command, group, option, state


@state
class Session:
    db: Path


@group("notes")
@option("db")
def notes(session: Session, db: Path = Path("notes.db")) -> Iterator[None]:
    """Keep notes."""
    session.db = db
    print(f"Opened {db}.")
    try:
        yield
    finally:
        print(f"Closed {db}.")


@command("add")
@argument("text")
def add(session: Session, text: str) -> str:
    """Add a note."""
    return f"Added {text!r} to {session.db}."


notes.add(add)

if __name__ == "__main__":
    notes()
```

```console
$ python notes.py --db work.db add milk
Opened work.db.
Closed work.db.
Added 'milk' to work.db.
$ python notes.py add milk --db work.db
error: --db belongs to 'notes'. Write it right after 'notes'.
Run 'notes add --help' for usage.
```

- When the command fails, or the run is stopped with Ctrl+C or SIGTERM, the exception is raised at `yield`. Code after a bare `yield` is skipped, so cleanup goes in `finally`.
- A group can't swallow the exception. Catching it is fine, but it's raised again.
- The result is written last, once cleanup has succeeded, so a failed cleanup never shows a result.
- A group's function yields once, or doesn't yield at all, and returns `None`.

### State

A `@state` class holds data for one run. cliron creates it, without arguments, the first time a function asks for it. Then every group, command and hook in the run that asks gets the same one. The next run gets a new one.

- The class must work without arguments. A field without a default, like `db` above, stays unset until a function sets it.
- A field can't default to a list, dict or set, since every run would share it. With `@dataclass`, use `field(default_factory=list)`.

### Hooks

```python
from cliron import Context, argument, command, hook, on


def started(ctx: Context) -> None:
    print(f"Running {' '.join(ctx.path)}.")


def finished() -> None:
    print("Done.")


@command("add")
@hook(on.start(), started)
@hook(on.exit(), finished)
@argument("text")
def add(text: str) -> str:
    """Add a note."""
    return f"Added {text!r}."


if __name__ == "__main__":
    add()
```

```console
$ python notes.py milk
Running add.
Done.
Added 'milk'.
```

| Hook                            | Runs                                                                        |
| ------------------------------- | --------------------------------------------------------------------------- |
| `@hook(on.start(), function)`   | Before the command or group, and before everything inside a group           |
| `@hook(on.success(), function)` | After it ended without an exception, or after its error hook handled one    |
| `@hook(on.error(), function)`   | When an exception leaves it, as [below](#handling-errors)                   |
| `@hook(on.exit(), function)`    | After it, whether it succeeded or not, unless one of its start hooks failed |

- These hooks go right below `@command` or `@group`, and run in the order they're written.
- A hook's function gets `Context` and `@state` classes by their annotations, like a command, and returns `None`, except an error hook.
- A hook that raises an exception fails the run, as the command would, unless an error hook handles it. The later hooks of the same event don't run.

A parameter annotated `Context` gets the run's context:

| Attribute    | Holds                                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `ctx.path`   | The names on the command line's path, in kebab-case, such as `("notes", "rename-tag")`, with aliases replaced by names |
| `ctx.values` | Each node's values by parameter name, defaults included, in the same order, so `ctx.values[-1]` is the command's       |

### Handling errors

```python
from pathlib import Path

from cliron import argument, command, hook, on


def missing(exc: FileNotFoundError) -> str:
    return f"There's no {exc.filename}."


@command("show")
@hook(on.error(), missing)
@argument("path")
def show(path: Path) -> str:
    """Show a note."""
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    show()
```

```console
$ python notes.py milk.txt; echo "exit code $?"
There's no milk.txt.
exit code 0
```

- An error hook's function takes the exception, annotated with the types it handles, such as `FileNotFoundError` or `KeyError | ValueError`. The first matching hook runs.
- What it returns becomes the command's result, so it's written to stdout and the run succeeds.
- It returns the type the command is annotated with, such as a `str` for `-> str`, or the run fails with exit code 1. A command annotated `-> str | None` lets it return `None`, which writes nothing.
- To fail instead, raise `SystemExit`. `raise SystemExit(f"There's no {exc.filename}.")` writes the message to stderr and exits with 1.
- A group's error hook covers everything inside it, and returns `None`, so the run succeeds without writing a result.
- An exception that no hook handles prints its traceback, and exits with 1.
- Error hooks never handle `SystemExit`, Ctrl+C or mistakes cliron finds in the CLI's code.

Below a parent or child, an error hook gives the parameter its value when the input is missing, or when reading, converting or checking it fails. It gets a `LookupError` when the input is missing, and a `ValueError` when it's invalid. It runs while the inputs are read. Mistakes in how the command line is written, such as `--width` without a value, stay errors.

```python
from cliron import command, env, hook, on


def default_width(exc: LookupError | ValueError) -> int:
    return 80


@command("show")
@env("notes_width")
@hook(on.error(), default_width)
def show(notes_width: int) -> str:
    """Show your notes."""
    return f"{notes_width} columns."


if __name__ == "__main__":
    show()
```

```console
$ python notes.py
80 columns.
$ NOTES_WIDTH=wide python notes.py
80 columns.
$ NOTES_WIDTH=120 python notes.py
120 columns.
```

### Exit codes

| Code | When                                                                                          |
| ---- | --------------------------------------------------------------------------------------------- |
| 0    | It worked, including help, `--version`, and errors that an error hook handled                 |
| 1    | An exception that nothing handled, shown with its traceback                                   |
| 1    | A mistake cliron found in the CLI's code, shown with where it was made                        |
| 1    | `raise SystemExit("message")`                                                                 |
| 1    | Output to a closed pipe, on Linux and macOS                                                   |
| 2    | Invalid input, an unknown or disabled command, or a group run without a command               |
| 130  | Ctrl+C, after `finally` blocks and exit hooks ran                                             |
| 143  | SIGTERM, after `finally` blocks and exit hooks ran, unless the program handles SIGTERM itself |

`raise SystemExit(3)` exits with 3.

### Async

Commands, groups, hooks, your own parents and children, function fallbacks and completion functions can all be `async def`. A group can be an async generator.

```python
import asyncio

from cliron import command


@command("fetch")
async def fetch() -> str:
    """Fetch notes."""
    await asyncio.sleep(0)
    return "Fetched."


if __name__ == "__main__":
    fetch()
```

```console
$ python notes.py
Fetched.
```

A run with an async function runs in an event loop of its own, so a CLI can't be called from inside a running loop. `enabled=` functions can't be async.

## 8. Testing

`cliron.testing.run` runs a CLI in your test, and returns its exit code and what it printed.

```python
from cliron import argument, command, fallback, option
from cliron.testing import run, validate


@command("add")
@argument("text")
@option("tag")
@fallback(env="NOTES_TAG")
def add(text: str, tag: str = "inbox") -> str:
    """Add a note."""
    return f"Added {text!r} to {tag}."


@command("login")
@option("user")
@fallback(prompt=True)
def login(user: str) -> str:
    """Sign in."""
    return f"Hello, {user}."


def test_add() -> None:
    result = run(add, ["milk"], env={})

    assert result.returncode == 0
    assert result.stdout == "Added 'milk' to inbox.\n"


def test_add_needs_text() -> None:
    result = run(add, [], env={})

    assert result.returncode == 2
    assert result.stderr == "error: TEXT is required.\nRun 'add --help' for usage.\n"


def test_add_reads_the_tag_from_the_environment() -> None:
    result = run(add, ["milk"], env={"NOTES_TAG": "home"})

    assert result.stdout == "Added 'milk' to home.\n"


def test_login_asks_for_the_user() -> None:
    result = run(login, [], input="ada\n", terminal=True)

    assert result.stdout == "Hello, ada.\n"
    assert result.stderr == "User: "


def test_the_cli_is_valid() -> None:
    validate(add)
    validate(login)
```

| `run(...)` takes | Default | For                                                                                                                      |
| ---------------- | ------- | ------------------------------------------------------------------------------------------------------------------------ |
| `cli`            |         | The command or group                                                                                                     |
| `args`           |         | The words after the program's name, as a list, such as `["tags", "rename", "home"]` for a command in groups              |
| `env=`           | `None`  | The environment, in place of `os.environ` until the run ends. `None` keeps yours, so your shell's variables count        |
| `input=`         | `None`  | The text piped in. `None` pipes nothing, and `""` is an empty pipe                                                       |
| `terminal=`      | `False` | Makes stdin a terminal, so prompts read their answers from `input`, one line each, and write their questions to `stderr` |

It returns a `subprocess.CompletedProcess` with `returncode`, `stdout` and `stderr`:

| When the CLI               | `run`                                                                                                      |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Succeeds                   | Returns 0                                                                                                  |
| Gets invalid input         | Returns 2, with the errors in `stderr`                                                                     |
| Raises `SystemExit(3)`     | Returns 3                                                                                                  |
| Raises another exception   | Raises it, so the test fails with its traceback                                                            |
| Has a mistake cliron finds | Raises it, as a `TypeError` or `ValueError`, or an `ImportError` for a lazy command that can't be imported |

Only what's written to `sys.stdout` and `sys.stderr` is captured. A CLI with async functions can't run inside an async test, since it runs its own event loop.

`validate` checks the definitions of every command and group in a CLI, including the ones no test runs, and imports the lazy ones. It raises the error a run would print. It doesn't run commands, groups or hooks, and doesn't call `enabled`.

## 9. Shell completion

Every CLI prints a completion script for bash, zsh or fish with `--completion`. Tell your users to add one line:

| Shell                                 | Line                                |
| ------------------------------------- | ----------------------------------- |
| Bash, in `~/.bashrc`                  | `eval "$(notes --completion bash)"` |
| Zsh, in `~/.zshrc`, after `compinit`  | `eval "$(notes --completion zsh)"`  |
| Fish, in `~/.config/fish/config.fish` | `notes --completion fish \| source` |

Commands, aliases, options and flags complete on their own, and so do the values of `@choices`, `Literal`, Enum names and paths. Below `@directory`, paths complete to directories only.

`completions=` on `@option` or `@argument` offers your own values instead:

```python
from cliron import command, option


def tags(typed: str) -> list[str]:
    return [tag for tag in ("home", "work", "shopping") if tag.startswith(typed)]


@command("add")
@option("tag", completions=tags)
@option("color", completions=["red", "green", "blue"])
def add(tag: str = "inbox", color: str = "red") -> str:
    """Add a note."""
    return f"Filed under {tag}, {color}."
```

- A function gets the text typed so far and returns the values. It runs on each Tab, and may be `async def`.
- To run it, completion runs the program, so the program must be [installed](#2-running-your-cli) under the name users type.
- If it raises an exception, nothing is offered.
- Completions don't limit what the parent accepts.

The script is made when the shell starts. That imports every enabled lazy command, and decides which commands `enabled` hides until the shell restarts.

## 10. Measuring

Set these when running any cliron CLI. Each prints a line on stderr when the run ends, even when it fails.

| Variable           | Prints                   | Units                 |
| ------------------ | ------------------------ | --------------------- |
| `CLIRON_TIME=ms`   | `time: 12.346 ms`        | `ns`, `us`, `ms`, `s` |
| `CLIRON_CPU=ms`    | `cpu: 11.872 ms`         | `ns`, `us`, `ms`, `s` |
| `CLIRON_MEMORY=mb` | `memory: 41.234 MB peak` | `b`, `kb`, `mb`, `gb` |

- Time and CPU time count from `import cliron`. Memory is the process's peak.
- Units are powers of 1000, and their case doesn't matter.
- An empty value or `0` turns one off. Any other value uses `ms`, or `mb` for memory.
- Under `cliron.testing.run`, only `env=` counts, and time counts from the call.
