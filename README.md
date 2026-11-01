# Cliron

[![PyPI](https://img.shields.io/pypi/v/cliron)](https://pypi.org/project/cliron/)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmarcusfrdk%2Fcliron%2Fmain%2Fpyproject.toml)](https://pypi.org/project/cliron/)
[![CI](https://github.com/marcusfrdk/cliron/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/marcusfrdk/cliron/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/marcusfrdk/cliron)](https://github.com/marcusfrdk/cliron/blob/main/LICENSE)

Everything you need to build your own CLI, giving you the features you'd expect out of the box, and lets you change any of them to fit your tool. All dependency free.

## Installation

```bash
pip install cliron
```

## Requirements

- **Python**: 3.11 or higher

## Quick start

```python
from cliron import argument, command, group, option


@group("notes")
def notes() -> None:
    """Keep notes."""


@command("add")
@argument("text")
@option("tag", "-t")
def add(text: str, tag: str = "inbox") -> str:
    """Add a note."""
    return f"Added {text!r} to {tag}."


notes.add(add)

if __name__ == "__main__":
    notes()
```

```console
$ python notes.py add milk -t shopping
Added 'milk' to shopping.
$ python notes.py ad milk
error: 'ad' isn't a notes command. Did you mean 'add'?
Run 'notes --help' for usage.
```

The [guide](GUIDE.md) shows how to use cliron, and the [reference](REFERENCE.md) describes every public function and class.

## Development

Install the virtual environment and development dependencies in order to start developing.

```bash
just sync
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute.

## License

This project is licensed under the MIT license. See the [LICENSE](https://github.com/marcusfrdk/cliron/blob/main/LICENSE) file for more information.
