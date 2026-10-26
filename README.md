# Cliron

[![PyPI](https://img.shields.io/pypi/v/cliron)](https://pypi.org/project/cliron/)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmarcusfrdk%2Fcliron%2Fmain%2Fpyproject.toml)](https://pypi.org/project/cliron/)
[![CI](https://github.com/marcusfrdk/cliron/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/marcusfrdk/cliron/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/marcusfrdk/cliron)](https://github.com/marcusfrdk/cliron/blob/main/LICENSE)

Everything you need to build your own CLI. Cliron gives you the features you'd expect out of the box, and lets you change any of them to fit your tool. It installs nothing else.

## Installation

```bash
pip install cliron
```

## Requirements

- **Python**: 3.11 or higher
- **uv**: 0.11 or higher
- **just**: 1.52 or higher

## Shell Completions

Every CLI built with cliron prints a completion script for bash, zsh or fish with `--completion`. Replace `mycli` with the name of your installed command.

### Bash

```bash
echo 'eval "$(mycli --completion bash)"' >> ~/.bashrc
```

### Zsh

```bash
echo 'autoload -Uz compinit && compinit' >> ~/.zshrc
echo 'eval "$(mycli --completion zsh)"' >> ~/.zshrc
```

Leave out the first line if your `~/.zshrc` already runs `compinit`.

### Fish

```bash
echo 'mycli --completion fish | source' >> ~/.config/fish/config.fish
```

## Development

```bash
just
just check
```

## License

This project is licensed under an MIT license, see the [LICENSE](https://github.com/marcusfrdk/cliron/blob/main/LICENSE) file for more information.
